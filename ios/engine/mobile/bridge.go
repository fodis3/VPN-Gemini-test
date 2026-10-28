// Package engine exposes only gomobile-supported string functions.
package engine

import native "vpngemini/engine"

func Parse(text string) string                 { return native.Parse(text) }
func Probe(request string) string              { return native.Probe(request) }
func Cancel(id string)                         { native.Cancel(id) }
func Subscription(address, hwid string) string { return native.Subscription(address, hwid) }
func NewHWID() string                          { return native.NewHWID() }
