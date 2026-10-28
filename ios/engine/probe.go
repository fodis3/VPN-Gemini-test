package engine

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var jobs sync.Map
var preCancelled sync.Map

type probeRequest struct {
	ID      string `json:"id"`
	Server  Server `json:"server"`
	Timeout int    `json:"timeout"`
}

const userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

// Cancel is safe to call from the main thread while Probe runs on a background thread.
func Cancel(id string) {
	if value, ok := jobs.Load(id); ok {
		value.(context.CancelFunc)()
		return
	}
	preCancelled.Store(id, true)
	time.AfterFunc(2*time.Minute, func() { preCancelled.Delete(id) })
}
func Probe(requestJSON string) string {
	var req probeRequest
	if e := json.Unmarshal([]byte(requestJSON), &req); e != nil {
		return failure(fmt.Errorf("Некорректный запрос проверки"))
	}
	req.Timeout = max(5, min(60, req.Timeout))
	if req.ID == "" {
		req.ID = uuid()
	}
	ctx, cancel := context.WithCancel(context.Background())
	if _, loaded := jobs.LoadOrStore(req.ID, context.CancelFunc(cancel)); loaded {
		cancel()
		return failure(fmt.Errorf("Проверка с таким ID уже запущена"))
	}
	defer jobs.Delete(req.ID)
	defer cancel()
	if _, ok := preCancelled.LoadAndDelete(req.ID); ok {
		cancel()
	}
	start := time.Now()
	result := probeAttempt(ctx, req.Server, req.Timeout, false)
	message := strings.ToLower(result.Detail)
	retry := result.Status == "TIMEOUT" || result.Status == "ERROR" && (strings.Contains(message, "message too long") || strings.Contains(message, "emsgsize") || strings.Contains(message, "packet too large") || strings.Contains(message, "quic: timeout") || strings.Contains(message, "handshake timeout") || strings.Contains(message, "no recent network activity"))
	if (req.Server.Protocol == "hy2" || req.Server.Protocol == "hysteria2") && result.HTTPCode == 0 && retry && ctx.Err() == nil {
		result = probeAttempt(ctx, req.Server, req.Timeout, true)
		result.Retried = true
		result.Detail = "Повтор QUIC: пакет 1200 байт. " + result.Detail
	}
	result.TotalMS = time.Since(start).Milliseconds()
	return encoded(result)
}
func probeAttempt(parent context.Context, s Server, timeout int, compat bool) Result {
	result := Result{Server: s, Status: "ERROR"}
	if s.Error != "" {
		result.Detail = s.Error
		return result
	}
	ctx, cancel := context.WithTimeout(parent, time.Duration(timeout)*time.Second)
	defer cancel()
	dial, closeCore, e := startCore(ctx, s, compat)
	if e != nil {
		return probeError(result, e, ctx)
	}
	defer closeCore()
	return fetchGemini(ctx, s, dial, nil)
}
func fetchGemini(ctx context.Context, s Server, dial dialFunc, tlsConfig *tls.Config) Result {
	result := Result{Server: s, Status: "ERROR"}
	var connectAt atomic.Int64
	var tlsMS atomic.Int64
	transport := &http.Transport{Proxy: nil, ForceAttemptHTTP2: false, TLSClientConfig: tlsConfig,
		DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
			connectAt.Store(time.Now().UnixNano())
			return dial(ctx, network, addr)
		}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if req.URL.Scheme != "https" {
			return fmt.Errorf("Небезопасное перенаправление")
		}
		if len(via) >= 8 {
			return fmt.Errorf("Слишком много перенаправлений")
		}
		return nil
	}}
	request, _ := http.NewRequestWithContext(ctx, "GET", "https://gemini.google.com/app", nil)
	request.Header.Set("User-Agent", userAgent)
	request.Header.Set("Accept-Language", "en-US,en;q=0.9")
	request.Header.Set("Cache-Control", "no-cache")
	trace := &httptrace.ClientTrace{TLSHandshakeDone: func(_ tls.ConnectionState, err error) {
		if err == nil && connectAt.Load() > 0 {
			tlsMS.Store(max(1, (time.Now().UnixNano()-connectAt.Load()+999999)/1000000))
		}
	}}
	request = request.WithContext(httptrace.WithClientTrace(request.Context(), trace))
	response, e := client.Do(request)
	if e != nil {
		return probeError(result, e, ctx)
	}
	defer response.Body.Close()
	body, e := io.ReadAll(io.LimitReader(response.Body, 8*1024*1024+1))
	if e != nil {
		return probeError(result, e, ctx)
	}
	if len(body) > 8*1024*1024 {
		return probeError(result, fmt.Errorf("Ответ превысил 8 МБ"), ctx)
	}
	result = classify(response.StatusCode, response.Request.URL.String(), string(body))
	result.Server = s
	result.Bytes = len(body)
	if ms := tlsMS.Load(); ms > 0 {
		result.PingMS = &ms
	}
	return result
}
func probeError(r Result, e error, ctx context.Context) Result {
	r.Status = "ERROR"
	var timeout net.Error
	if errors.Is(ctx.Err(), context.Canceled) {
		r.Status = "CANCELLED"
	} else if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.As(e, &timeout) && timeout.Timeout() {
		r.Status = "TIMEOUT"
	}
	r.Detail = sanitize(e.Error(), r.Server)
	return r
}
func sanitize(text string, s Server) string {
	for _, secret := range []string{s.Raw, s.Password, s.User, s.Params["obfs-password"], s.Params["obfs_password"]} {
		if len(secret) > 3 {
			text = strings.ReplaceAll(text, secret, "***")
		}
	}
	if len(text) > 1800 {
		text = text[:1800]
	}
	return text
}
