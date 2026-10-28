package engine

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

// Subscription fetches configuration data only; the URL is never returned in errors.
func Subscription(address, hwid string) string {
	u, e := url.Parse(address)
	if e != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil {
		return failure(fmt.Errorf("Укажите HTTPS-ссылку подписки"))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	request, _ := http.NewRequestWithContext(ctx, "GET", address, nil)
	ua := "v2rayN/6.67"
	if hwid != "" {
		ua += " HWID/" + hwid
		request.Header.Set("x-hwid", hwid)
		request.Header.Set("x-device-os", "iOS")
	}
	request.Header.Set("User-Agent", ua)
	request.Header.Set("Accept", "text/plain, application/json, */*")
	request.Header.Set("Accept-Language", "en-US,en;q=0.9")
	client := &http.Client{CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 8 || req.URL.Scheme != "https" {
			return fmt.Errorf("Некорректное перенаправление подписки")
		}
		// Device identity must never leak to another host on a redirect.
		if req.URL.Hostname() != via[0].URL.Hostname() {
			req.Header.Del("x-hwid")
			req.Header.Del("x-device-os")
			req.Header.Set("User-Agent", "v2rayN/6.67")
		}
		return nil
	}}
	response, e := client.Do(request)
	if e != nil {
		return failure(fmt.Errorf("Не удалось загрузить подписку. Проверьте сеть и доступ к поставщику."))
	}
	defer response.Body.Close()
	body, e := io.ReadAll(io.LimitReader(response.Body, 8*1024*1024+1))
	if e != nil || len(body) > 8*1024*1024 {
		return failure(fmt.Errorf("Не удалось прочитать подписку (лимит 8 МБ)"))
	}
	content, e := validateSubscription(response.StatusCode, string(body))
	if e != nil {
		return failure(e)
	}
	return Parse(content)
}
func validateSubscription(code int, body string) (string, error) {
	text := strings.TrimSpace(strings.TrimPrefix(body, "\ufeff"))
	lower := strings.ToLower(text)
	if strings.Contains(lower, "cloudflare") && regexp.MustCompile(`(?i)(?:error\s*(?:code\s*)?[:=]?\s*|<span[^>]*>)1002`).MatchString(text) {
		return "", fmt.Errorf("Cloudflare 1002: проверьте DNS подписки у поставщика")
	}
	var m map[string]any
	if json.Unmarshal([]byte(text), &m) == nil && m["outbounds"] == nil && m["protocol"] == nil && m["type"] == nil {
		if m["code"] != nil || m["errorCode"] != nil || m["statusCode"] != nil || m["error"] != nil || m["success"] == false {
			c := str(m["code"])
			if c == "" {
				c = str(m["errorCode"])
			}
			if c == "" {
				c = str(m["statusCode"])
			}
			if !regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`).MatchString(c) {
				c = ""
			}
			codeText := ""
			if c != "" {
				codeText = " · код " + c
			}
			return "", fmt.Errorf("Поставщик отклонил подписку%s. Проверьте привязанный HWID, срок и лимит устройств", codeText)
		}
	}
	if code < 200 || code > 299 {
		return "", fmt.Errorf("Подписка ответила HTTP %d. Проверьте доступ, HWID и лимит устройств", code)
	}
	if text == "" {
		return "", fmt.Errorf("Сервер вернул пустую подписку")
	}
	if strings.HasPrefix(lower, "<!doctype html") || strings.HasPrefix(lower, "<html") || strings.Contains(lower, "<body") {
		return "", fmt.Errorf("Вместо конфигураций получена веб-страница. Нужна ссылка импорта подписки")
	}
	if len(text) < 1500 && regexp.MustCompile(`(?i)(?:error|ошибка)\s*[:=]?\s*1002`).MatchString(text) {
		return "", fmt.Errorf("Поставщик вернул ошибку 1002. Проверьте условия доступа у поставщика")
	}
	return text, nil
}
