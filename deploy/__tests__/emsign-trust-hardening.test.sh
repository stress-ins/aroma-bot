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
make_cert zeroca 0x0 'DigiCert Serial Zero Test CA'
serials=$(sed -n "s/^readonly serials='\(.*\)'/\1/p" "$HELPER")
n=0
for serial in $serials; do n=$((n+1)); make_cert "blocked$n" "0x$serial" "Blocked CA $n"; done
test "$n" -eq 19
cp "$ROOT/usr/share/ca-certificates/test/emsign.crt" "$ROOT/usr/local/share/ca-certificates/local-emsign.crt"
ln -s "$ROOT/usr/share/ca-certificates/test/emsign.crt" "$ROOT/usr/local/share/ca-certificates/linked-emsign.crt"
cat > "$ROOT/bin/update-ca-certificates" <<'UPDATE'
#!/bin/sh
set -eu
test "$1" = --fresh
: > "$EMSIGN_TRUST_ROOT/etc/ssl/certs/ca-certificates.crt"
while IFS= read -r entry; do
  case "$entry" in ''|'#'*|'!'*) continue;; esac
  cat "$EMSIGN_TRUST_ROOT/usr/share/ca-certificates/$entry" >> "$EMSIGN_TRUST_ROOT/etc/ssl/certs/ca-certificates.crt"
done < "$EMSIGN_TRUST_ROOT/etc/ca-certificates.conf"
if [ -n "${EMSIGN_TEST_INJECT_CA:-}" ]; then cat "$EMSIGN_TEST_INJECT_CA" >> "$EMSIGN_TRUST_ROOT/etc/ssl/certs/ca-certificates.crt"; fi
UPDATE
chmod 0755 "$ROOT/bin/update-ca-certificates"
for pass in 1 2; do
  PATH="$ROOT/bin:$PATH" EMSIGN_TRUST_ROOT="$ROOT" bash "$HELPER" --ca-store-only
done
bundle="$ROOT/etc/ssl/certs/ca-certificates.crt"
openssl verify -CAfile "$bundle" "$ROOT/usr/share/ca-certificates/test/comodo.crt" "$ROOT/usr/share/ca-certificates/test/zeroca.crt"
for cert in "$ROOT/usr/share/ca-certificates/test/"*.crt; do
  [[ "$cert" == */comodo.crt || "$cert" == */zeroca.crt ]] && continue
  if openssl verify -CAfile "$bundle" "$cert" > /dev/null 2>&1; then echo "Still trusted: $cert" >&2; exit 1; fi
done
test ! -e "$ROOT/usr/local/share/ca-certificates/local-emsign.crt"
test -s "$ROOT/usr/local/share/ca-certificates/local-emsign.crt.emsign-distrusted"
python3 - <<'PY'
import os, pathlib, subprocess, json
root = pathlib.Path(os.environ['ROOT']).resolve()
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
# Guard every deploy-owned unit template against future bypass on install.
for unit in pathlib.Path(os.environ['HELPER']).parent.rglob('*.service'):
    for line in unit.read_text().splitlines():
        import re
        match = re.match(r'^Exec(?:Start(?:Pre|Post)?|Reload|Stop(?:Post)?)=(.*)', line)
        if match and match[1].strip():
            assert re.match(r'^[-+!:|]*/usr/local/libexec/emsign-exec ', match[1]), (unit, line)
# Exercise installed source migration without a systemd manager.
source = root / 'kartracers-test.service'
original = """[Service]
EnvironmentFile=/secret/options.env
ExecStartPre=-+/bin/true
ExecStart=/usr/bin/node --trace-warnings \\
 app.js
ExecStartPost=:/bin/sh -c 'echo "$${VALUE}"'
"""
source.write_text(original)
legacy = root / 'kartracers-test.service.d/90-emsign-trust.conf'
legacy.parent.mkdir()
legacy.write_text('[Service]\nExecStart=/old/stale-command\n')
unrelated = root / 'unrelated.service'
unrelated.write_text('[Service]\nExecStart=/bin/true\n')
def mock(args, **kwargs):
    if args[1] == 'cat':
        return f'# {source}\n{source.read_text()}\n# {legacy}\n{legacy.read_text() if legacy.exists() else ""}'
    return 'kartracers-test.service enabled\nunrelated.service enabled\n'
subprocess.check_output = mock
installer = helper.split("python3 - <<'PYINSTALL'\n", 1)[1].split('\nPYINSTALL', 1)[0]
installer = installer.replace("allowed = ('/etc/systemd/system/', '/run/systemd/system/', '/usr/lib/systemd/system/', '/lib/systemd/system/')", 'allowed = (str(root) + "/",)')
exec(compile(installer, '<installer>', 'exec'))
wrapped = source.read_text()
assert 'ExecStart=/usr/local/libexec/emsign-exec /usr/bin/node --trace-warnings' in wrapped
assert 'ExecStartPre=-+/usr/local/libexec/emsign-exec /bin/true' in wrapped
assert 'ExecStartPost=:/usr/local/libexec/emsign-exec /bin/sh' in wrapped
assert 'EnvironmentFile=/secret/options.env' in wrapped
assert '"$${VALUE}"' in wrapped
assert not legacy.exists()
assert unrelated.read_text() == '[Service]\nExecStart=/bin/true\n'
exec(compile(installer, '<installer>', 'exec'))
assert source.read_text() == wrapped
# Future deploy replaces source with a fresh wrapped command; no persistent
# snapshot exists to hide that command or pin the old app argument.
source.write_text(wrapped.replace('app.js', 'new-app.js'))
exec(compile(installer, '<installer>', 'exec'))
assert 'new-app.js' in source.read_text() and '/old/stale-command' not in source.read_text()
# Reject app-repository symlinks instead of modifying user-owned source.
app_source = root.parent / (root.name + '-app.service')
app_source.write_text(original)
try:
    source.unlink()
    source.symlink_to(app_source)
    try:
        exec(compile(installer, '<installer>', 'exec'))
        raise AssertionError('accepted external symlink')
    except SystemExit as error:
        assert 'outside systemd config' in str(error)
    assert app_source.read_text() == original
finally:
    source.unlink()
    app_source.unlink()
# Known production checkout unit links are explicitly authorized; preserve the
# symlink and back up the target, while the foreign-link guard above remains.
project_units = root.parent / (root.name + '-known-project-units')
project_units.mkdir()
project_target = project_units / source.name
project_target.write_text(original)
source.symlink_to(project_target)
try:
    linked_installer = installer.replace("pathlib.Path('/opt/kartracers-site/deploy/systemd')", 'project_units')
    exec(compile(linked_installer, '<linked-installer>', 'exec'))
    assert source.is_symlink()
    assert '/usr/local/libexec/emsign-exec' in project_target.read_text()
    assert project_target.with_name(project_target.name + '.emsign-before').read_text() == original
finally:
    source.unlink()
    for entry in project_units.iterdir(): entry.unlink()
    project_units.rmdir()

print('PASS: wrapper options, in-place commands/prefixes/EnvFiles, fresh deploy command, idempotence, external source guard')
PY
test -L "$ROOT/usr/local/share/ca-certificates/linked-emsign.crt.emsign-distrusted"
test -s "$ROOT/usr/share/ca-certificates/test/emsign.crt"
if PATH="$ROOT/bin:$PATH" EMSIGN_TRUST_ROOT="$ROOT" EMSIGN_TEST_INJECT_CA="$ROOT/usr/share/ca-certificates/test/emsign.crt" bash "$HELPER" --ca-store-only > "$ROOT/injected.log" 2>&1; then
  echo 'ERROR: accepted blocked certificate in generated bundle' >&2; exit 1
fi
grep -q 'blocked certificate remains in generated bundle' "$ROOT/injected.log"
# A .crt with multiple certificates must never be classified by only its first.
cat "$ROOT/usr/share/ca-certificates/test/comodo.crt" "$ROOT/usr/share/ca-certificates/test/emsign.crt" > "$ROOT/usr/local/share/ca-certificates/mixed.crt"
if PATH="$ROOT/bin:$PATH" EMSIGN_TRUST_ROOT="$ROOT" bash "$HELPER" --ca-store-only > "$ROOT/multi.log" 2>&1; then
  echo 'ERROR: accepted a multi-certificate local CA file' >&2; exit 1
fi
grep -q 'exactly one PEM certificate' "$ROOT/multi.log"
echo 'PASS: actual verification rejects all 19 serials and emSign; unrelated Comodo retained; mixed PEM rejected'
