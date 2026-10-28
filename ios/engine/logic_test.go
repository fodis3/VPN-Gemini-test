package engine

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestCountryFormats(t *testing.T) {
	tests := []struct{ html, want string }{
		{`{"vXmutd":"US"}`, "US"},
		{`{"vXmutd":"%.@.\"RU\",\"redacted\",\"redacted\"]"}`, "RU"},
		{`{"vXmutd":"%.@.\u0022FI\u0022,\u0022redacted\u0022]"}`, "FI"},
		{`{\"vXmutd\":\"DE\"}`, "DE"},
		{`{"vXmutd":"ZZ","other":"US"}`, ""},
		{`{"vXmutd":"broken","other":"US"}`, ""},
		{`vXmutd random US text`, ""},
		{`{'vXmutd':'PL'}`, "PL"},
	}
	for i, test := range tests {
		if got := extractCountry(test.html); got != test.want {
			t.Errorf("case %d: got %q want %q", i, got, test.want)
		}
	}
}
func TestResponseParity(t *testing.T) {
	for _, test := range []struct {
		code              int
		url, html, status string
	}{
		{200, "https://gemini.google.com/app", `{"vXmutd":"US"}`, "OK"},
		{200, "https://gemini.google.com/app", `{"vXmutd":"RU"}`, "BLOCKED"},
		{200, "https://gemini.google.com/app", `{"vXmutd":"HK"}`, "OK"},
		{200, "https://gemini.google.com/app", `{"vXmutd":"CN"}`, "LOGIN"},
		{200, "https://gemini.google.com/app", `BardChatUi geminiweb-pa`, "UNKNOWN"},
		{200, "https://gemini.google.com/app", `Gemini isn't currently supported in your country`, "BLOCKED"},
		{200, "https://gemini.google.com/app", `<script>"not supported in your country"</script>{"vXmutd":"PL"}`, "OK"},
		{200, "https://accounts.google.com/login", "", "LOGIN"},
		{200, "https://www.google.com/sorry/index", "", "CAPTCHA"},
		{429, "https://gemini.google.com/app", "", "RATE_LIMIT"},
		{503, "https://gemini.google.com/app", `{"vXmutd":"US"}`, "ERROR"},
		{200, "https://example.org", `{"vXmutd":"US"}`, "UNKNOWN"},
	} {
		if got := classify(test.code, test.url, test.html); got.Status != test.status {
			t.Errorf("%d %s: %s != %s", test.code, test.url, got.Status, test.status)
		}
	}
}
func TestImportPreservesEightyRecordsAndDuplicates(t *testing.T) {
	lines := []string{}
	for i := range 80 {
		scheme := "vless"
		if i >= 75 {
			scheme = "unknown"
		}
		lines = append(lines, fmt.Sprintf("%s://00000000-0000-4000-8000-000000000001@example.org:443#Server%d", scheme, i))
	}
	text := base64.StdEncoding.EncodeToString([]byte(strings.Join(lines, "\n")))
	servers, e := parse(text, 0)
	if e != nil || len(servers) != 80 {
		t.Fatal("80 records must survive", e)
	}
	bad := 0
	for _, s := range servers {
		if s.Error != "" {
			bad++
		}
	}
	if bad != 5 {
		t.Fatal("Unsupported records lost")
	}
	dup, e := parse(lines[0]+"\n"+lines[0]+"\nbroken", 0)
	if e != nil || len(dup) != 3 || dup[0].ID == dup[1].ID || dup[2].Error == "" {
		t.Fatal("Duplicates or invalid lines were lost")
	}
}
func TestCredentialsAndTransports(t *testing.T) {
	ss := base64.RawStdEncoding.EncodeToString([]byte("aes-128-gcm:p+a:ss"))
	s, e := parseURI("ss://" + ss + "@example.org:8388#Test")
	if e != nil || s.Password != "p+a:ss" {
		t.Fatal("SS credentials changed", e)
	}
	hy, e := parseURI("hysteria2://user%3Apass+word@example.org:25801/?insecure=1&obfs=salamander&obfs-password=p%2Ba%3Ass")
	if e != nil {
		t.Fatal(e)
	}
	if hy.Password != "user:pass+word" || hy.Params["obfs-password"] != "p+a:ss" {
		t.Fatal("Hysteria credentials changed")
	}
	var config map[string]any
	json.Unmarshal(coreConfig(hy, []string{"192.0.2.1"}, true), &config)
	out := first(config["outbounds"])
	if out["initial_packet_size"] != float64(1200) || out["disable_chrome_parrot"] != true || out["disable_path_mtu_discovery"] != true {
		t.Fatal("Unsafe QUIC retry profile")
	}
	tls := asMap(out["tls"])
	if tls["server_name"] != "example.org" || tls["insecure"] != true {
		t.Fatal("TLS settings changed")
	}
	grpc, e := parseURI("vless://00000000-0000-4000-8000-000000000001@example.org:443?type=grpc&serviceName=api&authority=cdn.example.org&security=tls")
	if e != nil {
		t.Fatal(e)
	}
	json.Unmarshal(coreConfig(grpc, nil, false), &config)
	stream := asMap(first(config["outbounds"])["streamSettings"])
	g := asMap(stream["grpcSettings"])
	if g["authority"] != "cdn.example.org" || g["serviceName"] != "api" {
		t.Fatal("gRPC settings lost")
	}
}
func TestHTTPSUsesRemoteTLSAndDecodedBody(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `<title>Gemini</title>{"vXmutd":"%.@.\"US\",\"redacted\"]"}`)
	}))
	defer upstream.Close()
	pool := x509.NewCertPool()
	pool.AddCert(upstream.Certificate())
	dial := func(ctx context.Context, network, address string) (net.Conn, error) {
		time.Sleep(100 * time.Millisecond)
		return (&net.Dialer{}).DialContext(ctx, "tcp", strings.TrimPrefix(upstream.URL, "https://"))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	r := fetchGemini(ctx, Server{}, dial, &tls.Config{RootCAs: pool, ServerName: "example.com"})
	if r.Status != "OK" || r.Country != "US" || r.PingMS == nil || *r.PingMS < 100 {
		t.Fatalf("HTTPS/TLS invalid: %+v", r)
	}
	// A trust failure must never turn into a positive result.
	bad := fetchGemini(ctx, Server{}, dial, nil)
	if bad.Status == "OK" || bad.PingMS != nil {
		t.Fatal("TLS verification bypassed")
	}
}
func TestSubscriptionErrors(t *testing.T) {
	for _, body := range []string{`{"code":1002,"success":false}`, `<html>challenge</html>`, `error 1002`, ""} {
		if _, e := validateSubscription(200, body); e == nil {
			t.Fatal("Invalid subscription accepted")
		}
	}
	if _, e := validateSubscription(403, "denied"); e == nil {
		t.Fatal("HTTP error accepted")
	}
	if _, e := validateSubscription(200, "vless://test"); e != nil {
		t.Fatal(e)
	}
	if _, e := validateSubscription(200, "vless://test@cloudflare.example:1002"); e != nil {
		t.Fatal("Configuration mistaken for Cloudflare error", e)
	}
	if _, e := validateSubscription(200, `{"statusCode":1002}`); e == nil || !strings.Contains(e.Error(), "1002") {
		t.Fatal("Provider statusCode lost")
	}
}
func TestCancelBeforeNativeWorkerStarts(t *testing.T) {
	id := uuid()
	Cancel(id)
	r := Probe(encoded(probeRequest{ID: id, Timeout: 5, Server: Server{Protocol: "direct"}}))
	var value Result
	if json.Unmarshal([]byte(r), &value) != nil || value.Status != "CANCELLED" {
		t.Fatal("Pre-start cancellation lost")
	}
}
func TestLiveParity(t *testing.T) {
	cases := os.Getenv("VPN_GEMINI_LIVE_CASES")
	if cases == "" {
		t.Skip("Live credentials are supplied only through the process environment")
	}
	var entries []struct {
		URI      string `json:"uri"`
		Expected string `json:"expected"`
	}
	if e := json.Unmarshal([]byte(cases), &entries); e != nil {
		t.Fatal("Invalid live cases")
	}
	for i, entry := range entries {
		s, e := parseURI(entry.URI)
		if e != nil {
			t.Fatal("Live import failed")
		}
		var r Result
		json.Unmarshal([]byte(Probe(encoded(probeRequest{ID: uuid(), Server: s, Timeout: 20}))), &r)
		t.Logf("Live case %d: HTTP %d, Google %s, status %s, retry %t", i, r.HTTPCode, r.Country, r.Status, r.Retried)
		if r.Status != entry.Expected {
			t.Fatalf("Live case %d: expected %s, got %s: %s", i, entry.Expected, r.Status, r.Detail)
		}
	}
}
