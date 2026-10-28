#!/usr/bin/env bash
set -euo pipefail
: "${APPLE_CERTIFICATE_BASE64:?Missing certificate secret}"
: "${APPLE_CERTIFICATE_PASSWORD:?Missing certificate password}"
: "${APPLE_PROFILE_BASE64:?Missing provisioning profile}"
: "${APPLE_TEAM_ID:?Missing Apple team ID}"
keychain="$RUNNER_TEMP/vpngemini-signing.keychain-db"
password="$(openssl rand -hex 24)"
cleanup() { security delete-keychain "$keychain" 2>/dev/null || true; rm -f "$RUNNER_TEMP/vpngemini.p12" "$RUNNER_TEMP/vpngemini.mobileprovision"; }
trap cleanup EXIT
printf '%s' "$APPLE_CERTIFICATE_BASE64" | base64 --decode > "$RUNNER_TEMP/vpngemini.p12"
printf '%s' "$APPLE_PROFILE_BASE64" | base64 --decode > "$RUNNER_TEMP/vpngemini.mobileprovision"
security create-keychain -p "$password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$password" "$keychain"
security import "$RUNNER_TEMP/vpngemini.p12" -P "$APPLE_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$keychain"
security set-key-partition-list -S apple-tool:,apple: -k "$password" "$keychain"
security list-keychains -d user -s "$keychain" login.keychain-db
security cms -D -i "$RUNNER_TEMP/vpngemini.mobileprovision" > "$RUNNER_TEMP/profile.plist"
profileID=$(/usr/libexec/PlistBuddy -c 'Print UUID' "$RUNNER_TEMP/profile.plist")
mkdir -p "$HOME/Library/MobileDevice/Provisioning Profiles"
cp "$RUNNER_TEMP/vpngemini.mobileprovision" "$HOME/Library/MobileDevice/Provisioning Profiles/$profileID.mobileprovision"
python3 - <<'PY'
import os,plistlib
profile=plistlib.load(open(os.environ['RUNNER_TEMP']+'/profile.plist','rb'))
method='debugging' if profile.get('Entitlements',{}).get('get-task-allow') else 'release-testing'
bundle=profile['Entitlements']['application-identifier'].split('.',1)[1]
if bundle!='ru.vpngemini.ios':raise SystemExit('Profile must match ru.vpngemini.ios')
plistlib.dump({'method':method,'signingStyle':'manual','teamID':os.environ['APPLE_TEAM_ID'],
 'provisioningProfiles':{'ru.vpngemini.ios':profile['UUID']}},open('build/ExportOptions.plist','wb'))
PY
identity=$(security find-identity -v -p codesigning "$keychain" | awk '/[0-9A-F]{40}/ {print $2; exit}')
test -n "$identity"
xcodebuild archive -project VPNGemini.xcodeproj -scheme VPNGemini \
  -destination 'generic/platform=iOS' -archivePath build/Signed.xcarchive \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM="$APPLE_TEAM_ID" \
  PROVISIONING_PROFILE_SPECIFIER="$profileID" CODE_SIGN_IDENTITY="$identity"
xcodebuild -exportArchive -archivePath build/Signed.xcarchive -exportPath build/signed -exportOptionsPlist build/ExportOptions.plist
cp build/signed/*.ipa build/VPN-Gemini-iOS-4.0.0-signed.ipa
