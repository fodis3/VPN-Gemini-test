package engine

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

type Server struct {
	ID       string            `json:"id"`
	Name     string            `json:"name"`
	Protocol string            `json:"protocol"`
	Host     string            `json:"host"`
	Port     int               `json:"port"`
	User     string            `json:"user"`
	Password string            `json:"password"`
	Params   map[string]string `json:"params"`
	Raw      string            `json:"raw"`
	Outbound map[string]any    `json:"outbound,omitempty"`
	Engine   string            `json:"engine"`
	Error    string            `json:"error"`
}
type Result struct {
	Server   Server `json:"server"`
	Status   string `json:"status"`
	Country  string `json:"country"`
	PingMS   *int64 `json:"pingMs,omitempty"`
	TotalMS  int64  `json:"totalMs"`
	Detail   string `json:"detail"`
	HTTPCode int    `json:"httpCode"`
	FinalURL string `json:"finalUrl"`
	Bytes    int    `json:"bytes"`
	Title    string `json:"title"`
	Retried  bool   `json:"retried"`
}

func uuid() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	h := hex.EncodeToString(b[:])
	return fmt.Sprintf("%s-%s-%s-%s-%s", h[:8], h[8:12], h[12:16], h[16:20], h[20:])
}
func encoded(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return `{"error":"Ошибка сериализации"}`
	}
	return string(b)
}
func failure(err error) string { return encoded(map[string]any{"error": err.Error()}) }
func NewHWID() string          { return uuid() }
