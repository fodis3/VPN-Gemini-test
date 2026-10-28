package engine

import (
	"context"
	"fmt"
	"net"

	box "github.com/sagernet/sing-box"
	"github.com/sagernet/sing-box/adapter/certificate"
	"github.com/sagernet/sing-box/adapter/endpoint"
	"github.com/sagernet/sing-box/adapter/inbound"
	"github.com/sagernet/sing-box/adapter/outbound"
	boxservice "github.com/sagernet/sing-box/adapter/service"
	"github.com/sagernet/sing-box/dns"
	"github.com/sagernet/sing-box/dns/transport/hosts"
	"github.com/sagernet/sing-box/dns/transport/local"
	"github.com/sagernet/sing-box/option"
	"github.com/sagernet/sing-box/protocol/hysteria2"
	"github.com/sagernet/sing-box/protocol/tuic"
	singjson "github.com/sagernet/sing/common/json"
	M "github.com/sagernet/sing/common/metadata"
	_ "github.com/xtls/xray-core/app/dispatcher"
	_ "github.com/xtls/xray-core/app/dns"
	_ "github.com/xtls/xray-core/app/log"
	_ "github.com/xtls/xray-core/app/proxyman/inbound"
	_ "github.com/xtls/xray-core/app/proxyman/outbound"
	_ "github.com/xtls/xray-core/app/router"
	xnet "github.com/xtls/xray-core/common/net"
	xcore "github.com/xtls/xray-core/core"
	_ "github.com/xtls/xray-core/infra/conf/serial"
	_ "github.com/xtls/xray-core/main/json"
	_ "github.com/xtls/xray-core/proxy/blackhole"
	_ "github.com/xtls/xray-core/proxy/freedom"
	_ "github.com/xtls/xray-core/proxy/shadowsocks"
	_ "github.com/xtls/xray-core/proxy/trojan"
	_ "github.com/xtls/xray-core/proxy/vless/outbound"
	_ "github.com/xtls/xray-core/proxy/vmess/outbound"
	_ "github.com/xtls/xray-core/transport/internet/grpc"
	_ "github.com/xtls/xray-core/transport/internet/httpupgrade"
	_ "github.com/xtls/xray-core/transport/internet/reality"
	_ "github.com/xtls/xray-core/transport/internet/splithttp"
	_ "github.com/xtls/xray-core/transport/internet/tcp"
	_ "github.com/xtls/xray-core/transport/internet/tls"
	_ "github.com/xtls/xray-core/transport/internet/websocket"
)

type dialFunc func(context.Context, string, string) (net.Conn, error)

func startCore(ctx context.Context, s Server, compat bool) (dialFunc, func(), error) {
	if s.Protocol == "direct" {
		d := &net.Dialer{}
		return d.DialContext, func() {}, nil
	}
	var addresses []string
	if s.Engine == "singbox" {
		ips, e := net.DefaultResolver.LookupIPAddr(ctx, s.Host)
		if e != nil {
			return nil, nil, fmt.Errorf("DNS VPN-сервера: %w", e)
		}
		for _, ip := range ips {
			addresses = append(addresses, ip.String())
		}
	}
	config := coreConfig(s, addresses, compat)
	if len(config) == 0 {
		return nil, nil, fmt.Errorf("Протокол не поддерживается")
	}
	if s.Engine == "singbox" {
		outs := outbound.NewRegistry()
		hysteria2.RegisterOutbound(outs)
		tuic.RegisterOutbound(outs)
		dnsRegistry := dns.NewTransportRegistry()
		hosts.RegisterTransport(dnsRegistry)
		local.RegisterTransport(dnsRegistry)
		coreCtx := box.Context(ctx, inbound.NewRegistry(), outs, endpoint.NewRegistry(), dnsRegistry, boxservice.NewRegistry(), certificate.NewRegistry())
		opts, e := singjson.UnmarshalExtendedContext[option.Options](coreCtx, config)
		if e != nil {
			return nil, nil, e
		}
		instance, e := box.New(box.Options{Context: coreCtx, Options: opts})
		if e != nil {
			return nil, nil, e
		}
		if e = instance.Start(); e != nil {
			instance.Close()
			return nil, nil, e
		}
		proxy, ok := instance.Outbound().Outbound("proxy")
		if !ok {
			instance.Close()
			return nil, nil, fmt.Errorf("Нет outbound proxy")
		}
		return func(ctx context.Context, network, address string) (net.Conn, error) {
			return proxy.DialContext(ctx, network, M.ParseSocksaddr(address))
		}, func() { instance.Close() }, nil
	}
	instance, e := xcore.StartInstance("json", config)
	if e != nil {
		return nil, nil, e
	}
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		dest, e := xnet.ParseDestination("tcp:" + address)
		if e != nil {
			return nil, e
		}
		return xcore.Dial(ctx, instance, dest)
	}, func() { instance.Close() }, nil
}
