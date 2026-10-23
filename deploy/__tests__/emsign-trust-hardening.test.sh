#!/usr/bin/env bash
set -euo pipefail
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
HELPER="$(cd "$(dirname "$0")/.." && pwd)/emsign-trust-hardening.sh"
export ROOT HELPER
mkdir -p "$ROOT/etc/ssl/certs" "$ROOT/usr/share/ca-certificates/test" "$ROOT/usr/local/share/ca-certificates" "$ROOT/bin"
make_cert() {
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$ROOT/key" -out "$ROOT/usr/share/ca-certificates/test/$1.crt" -days 1 -set_serial "$2" -subj "/CN=$3" >/dev/null 2>&1
  echo "test/$1.crt" >> "$ROOT/etc/ca-certificates.conf"
}
make_cert emsign 0xABCD 'emSign Test Root'
make_cert comodo 0x1234 'Comodo AAA Certificate Services'
serials=$(sed -n "s/^readonly serials='\(.*\)'/\1/p" "$HELPER")
n=0
for serial in $serials; do n=$((n+1)); make_cert "blocked$n" "0x$serial" "Blocked CA $n"; done
test "$n" -eq 19
cp "$ROOT/usr/share/ca-certificates/test/emsign.crt" "$ROOT/usr/local/share/ca-certificates/local-emsign.crt"
cat > "$ROOT/bin/update-ca-certificates" <<'UPDATE'
#!/bin/sh
set -eu
test "$1" = --fresh
: > "$EMSIGN_TRUST_ROOT/etc/ssl/certs/ca-certificates.crt"
while IFS= read -r entry; do
  case "$entry" in ''|'#'*|'!'*) continue;; esac
  cat "$EMSIGN_TRUST_ROOT/usr/share/ca-certificates/$entry" >> "$EMSIGN_TRUST_ROOT/etc/ssl/certs/ca-certificates.crt"
done < "$EMSIGN_TRUST_ROOT/etc/ca-certificates.conf"
UPDATE
chmod 0755 "$ROOT/bin/update-ca-certificates"
for pass in 1 2; do
  PATH="$ROOT/bin:$PATH" EMSIGN_TRUST_ROOT="$ROOT" bash "$HELPER" --ca-store-only
done
bundle="$ROOT/etc/ssl/certs/ca-certificates.crt"
openssl verify -CAfile "$bundle" "$ROOT/usr/share/ca-certificates/test/comodo.crt"
for cert in "$ROOT/usr/share/ca-certificates/test/"*.crt; do
  [[ "$cert" == */comodo.crt ]] && continue
  if openssl verify -CAfile "$bundle" "$cert" > /dev/null 2>&1; then echo "Still trusted: $cert" >&2; exit 1; fi
done
test ! -e "$ROOT/usr/local/share/ca-certificates/local-emsign.crt"
test -s "$ROOT/usr/local/share/ca-certificates/local-emsign.crt.emsign-distrusted"
python3 - <<'PY'
import os, pathlib, subprocess, json
root = pathlib.Path(os.environ['ROOT'])
helper = pathlib.Path(os.environ['HELPER']).read_text()
wrapper = helper.split("cat > /usr/local/libexec/emsign-exec <<'EOF'\n", 1)[1].split('\nEOF', 1)[0]
path = root / 'wrapper'
path.write_text(wrapper)
path.chmod(0o755)
env = dict(os.environ, NODE_OPTIONS='--max-old-space-size=256', SSL_CERT_FILE='/bad')
result = json.loads(subprocess.check_output([str(path), 'python3', '-c', 'import os,json;print(json.dumps(dict(os.environ)))'], env=env))
assert result['NODE_OPTIONS'] == '--max-old-space-size=256 --use-openssl-ca'
assert result['SSL_CERT_FILE'] == result['REQUESTS_CA_BUNDLE'] == result['PIP_CERT'] == '/etc/ssl/certs/ca-certificates.crt'
assert result['SSL_CERT_DIR'] == '/etc/emsign/empty-ca-dir'
# Unknown extra roots fail visibly instead of being silently dropped.
extra = dict(env, NODE_EXTRA_CA_CERTS='/private/corporate.pem')
failed = subprocess.run([str(path), '/bin/true'], env=extra, capture_output=True)
assert failed.returncode != 0 and b'requires an audited clean bundle' in failed.stderr
original = subprocess.check_output
unit = '''[Service]
EnvironmentFile=/secret/options.env
ExecStartPre=-/bin/true
ExecStart=/usr/bin/node --trace-warnings app.js
ExecStartPost=/bin/sh -c 'echo "$${VALUE}"'
'''
def mock(args, **kwargs):
    if args[1] == 'cat': return unit
    return 'kartracers-test.service enabled\nunrelated.service enabled\n'
subprocess.check_output = mock
installer = helper.split("python3 - <<'PYINSTALL'\n", 1)[1].split('\nPYINSTALL', 1)[0]
installer = installer.replace("pathlib.Path('/etc/systemd/system')", 'root')
exec(compile(installer, '<installer>', 'exec'))
dropin = (root / 'kartracers-test.service.d/90-emsign-trust.conf').read_text()
assert 'ExecStart=/usr/local/libexec/emsign-exec /usr/bin/node --trace-warnings app.js' in dropin
assert 'ExecStartPre=-/usr/local/libexec/emsign-exec /bin/true' in dropin
assert 'EnvironmentFile=' not in dropin
assert '"$${VALUE}"' in dropin
assert not (root / 'unrelated.service.d').exists()
# Re-running ignores its own drop-in while rebuilding the original commands.
unit += '\n# /etc/systemd/system/kartracers-test.service.d/90-emsign-trust.conf\n' + dropin
exec(compile(installer, '<installer>', 'exec'))
assert (root / 'kartracers-test.service.d/90-emsign-trust.conf').read_text() == dropin
print('PASS: wrapper preserves inherited options; scoped command overrides retain args/EnvFiles, idempotent')
PY
# A .crt with multiple certificates must never be classified by only its first.
cat "$ROOT/usr/share/ca-certificates/test/comodo.crt" "$ROOT/usr/share/ca-certificates/test/emsign.crt" > "$ROOT/usr/local/share/ca-certificates/mixed.crt"
if PATH="$ROOT/bin:$PATH" EMSIGN_TRUST_ROOT="$ROOT" bash "$HELPER" --ca-store-only > "$ROOT/multi.log" 2>&1; then
  echo 'ERROR: accepted a multi-certificate local CA file' >&2; exit 1
fi
grep -q 'exactly one PEM certificate' "$ROOT/multi.log"
echo 'PASS: actual verification rejects all 19 serials and emSign; unrelated Comodo retained; mixed PEM rejected'
