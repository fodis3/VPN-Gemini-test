#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engine"
go mod download
go install github.com/sagernet/gomobile/cmd/gomobile@v0.1.13
go install github.com/sagernet/gomobile/cmd/gobind@v0.1.13
export PATH="$(go env GOPATH)/bin:$PATH"
gomobile init
mkdir -p ../Frameworks
# Both cores are linked by the same Go invocation: exactly one Go runtime.
gomobile bind -target=ios,iossimulator -iosversion=17.0 -tags=with_quic,with_utls \
  -ldflags='-s -w' -trimpath -o ../Frameworks/GeminiCore.xcframework ./mobile
