package engine

import (
	"context"
	"crypto/x509"
	"encoding/pem"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	box "github.com/sagernet/sing-box"
	"github.com/sagernet/sing-box/adapter/certificate"
	"github.com/sagernet/sing-box/adapter/endpoint"
	"github.com/sagernet/sing-box/adapter/inbound"
	"github.com/sagernet/sing-box/adapter/outbound"
	boxservice "github.com/sagernet/sing-box/adapter/service"
	"github.com/sagernet/sing-box/dns"
	"github.com/sagernet/sing-box/dns/transport/local"
	"github.com/sagernet/sing-box/option"
	"github.com/sagernet/sing-box/protocol/direct"
	"github.com/sagernet/sing-box/protocol/hysteria2"
	singjson "github.com/sagernet/sing/common/json"
	xcore "github.com/xtls/xray-core/core"
	_ "github.com/xtls/xray-core/proxy/vless/inbound"
)

func TestBothEmbeddedCoresActuallyTunnelTraffic(t *testing.T) {
	web := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, "through-selected-core") }))
	defer web.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	// Xray server and Xray client coexist in this same executable.
	listener, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()
	id := "00000000-0000-4000-8000-000000000001"
	config := m("log", m("loglevel", "none"), "inbounds", a(m("listen", "127.0.0.1", "port", port, "protocol", "vless", "settings", m("clients", a(m("id", id)), "decryption", "none"))), "outbounds", a(m("protocol", "freedom")))
	xserver, e := xcore.StartInstance("json", []byte(encoded(config)))
	if e != nil {
		t.Fatal(e)
	}
	defer xserver.Close()
	s, e := parseURI("vless://" + id + "@127.0.0.1:" + strconv.Itoa(port) + "?security=none")
	if e != nil {
		t.Fatal(e)
	}
	assertTunnel(t, ctx, s, false, web.URL)

	// The sing-box core is linked into the exact same Go process, with salamander and QUIC.
	certServer := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	defer certServer.Close()
	cert := certServer.TLS.Certificates[0]
	key, e := x509.MarshalPKCS8PrivateKey(cert.PrivateKey)
	if e != nil {
		t.Fatal(e)
	}
	certPEM := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Certificate[0]}))
	keyPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: key}))
	packet, e := net.ListenPacket("udp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	udpPort := packet.LocalAddr().(*net.UDPAddr).Port
	packet.Close()
	in := inbound.NewRegistry()
	hysteria2.RegisterInbound(in)
	out := outbound.NewRegistry()
	direct.RegisterOutbound(out)
	dnsRegistry := dns.NewTransportRegistry()
	local.RegisterTransport(dnsRegistry)
	serverCtx := box.Context(ctx, in, out, endpoint.NewRegistry(), dnsRegistry, boxservice.NewRegistry(), certificate.NewRegistry())
	cfg := m("log", m("disabled", true), "inbounds", a(m("type", "hysteria2", "listen", "127.0.0.1", "listen_port", udpPort,
		"users", a(m("password", "test-auth")), "obfs", m("type", "salamander", "password", "test-obfs"),
		"tls", m("enabled", true, "certificate", a(certPEM), "key", a(keyPEM)))), "outbounds", a(m("type", "direct")))
	opts, e := singjson.UnmarshalExtendedContext[option.Options](serverCtx, []byte(encoded(cfg)))
	if e != nil {
		t.Fatal(e)
	}
	hyserver, e := box.New(box.Options{Context: serverCtx, Options: opts})
	if e != nil {
		t.Fatal(e)
	}
	defer hyserver.Close()
	if e = hyserver.Start(); e != nil {
		t.Fatal(e)
	}
	hy, e := parseURI("hy2://test-auth@127.0.0.1:" + strconv.Itoa(udpPort) + "/?insecure=1&obfs=salamander&obfs-password=test-obfs")
	if e != nil {
		t.Fatal(e)
	}
	assertTunnel(t, ctx, hy, false, web.URL)
	assertTunnel(t, ctx, hy, true, web.URL)
}
func assertTunnel(t *testing.T, ctx context.Context, s Server, compat bool, address string) {
	t.Helper()
	dial, closeCore, e := startCore(ctx, s, compat)
	if e != nil {
		t.Fatal(e)
	}
	defer closeCore()
	transport := &http.Transport{DialContext: dial}
	defer transport.CloseIdleConnections()
	request, _ := http.NewRequestWithContext(ctx, "GET", address, nil)
	response, e := (&http.Client{Transport: transport}).Do(request)
	if e != nil {
		t.Fatal(e)
	}
	defer response.Body.Close()
	body, e := io.ReadAll(response.Body)
	if e != nil || string(body) != "through-selected-core" {
		t.Fatal("Native tunnel failed", e)
	}
}
