#!/usr/bin/env bash
# Remove only the disclosed emSign CA certificates from Debian's generated
# trust bundle. Other anchors, including Comodo AAA, remain trusted.
set -euo pipefail
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --ca-store-only ) ]] || { echo "usage: $0 [--ca-store-only]" >&2; exit 1; }

readonly root=${EMSIGN_TRUST_ROOT:-}
readonly config="${root}/etc/ca-certificates.conf"
readonly source_dir="${root}/usr/share/ca-certificates"
readonly local_dir="${root}/usr/local/share/ca-certificates"
readonly bundle="${root}/etc/ssl/certs/ca-certificates.crt"

die() { echo "emsign-trust: FATAL: $*" >&2; exit 1; }
[[ -n "$root" || -r /etc/debian_version ]] || die "Debian-family host required"
[[ -f "$config" && -d "$source_dir" ]] || die "ca-certificates configuration missing"
command -v openssl >/dev/null || die "openssl is required"
command -v update-ca-certificates >/dev/null || die "update-ca-certificates is required"
if [[ -z "$root" && "${1:-}" != --ca-store-only ]]; then command -v python3 >/dev/null || die "python3 is required"; fi
if [[ -z "$root" ]]; then command -v systemctl >/dev/null || die "systemd is required"; fi

# Exact serials supplied for this incident. Normalize case and leading zeroes
# before matching; issuer is intentionally not part of the key.
readonly serials='A4AEE678F23362B4C0E460B772F214 6CADA367FB1C100088120EA202D568 C7C41EFE92D825F05EAE841A4A82C1 588B2E3C2BB8CDA13E1A1209254321 296926C227A3A1526392B19482A504 8009928A64107601AF05FA2F19F109 7818933F8F85B4619A2B35FBA83D0A 544B7F922C31AE220A4A922916F6E6 A024FDF4BA665C785CE4A020483858B7 91F347F1A5B7D39962B95E0EE4E299D1 D8F8685E4F2BD9D82402A85A1C1EB731 05F078752DECE7A1BB8595D303167171 41E32B73AC185D6CE0D7480BACF84E69 D6A5EF613B390F32EF9CDF349F772841 E94223BDE92F914E5AB9ACABFDAC3710 8D5A4811939EF447D77111CDD9849AE9 0E760672F143459FC8FE0AB0BC05E394 018FCEC927C116F59C997EDC0CCD2E2B 3CF607A968700EDA8B84'
declare -A blocked=()

normalize_serial() {
  local value=${1^^}
  value=${value//:/}
  value=${value#0}
  while [[ "$value" == 0* && ${#value} -gt 1 ]]; do value=${value#0}; done
  printf '%s' "$value"
}

for serial in $serials; do blocked["$(normalize_serial "$serial")"]=1; done

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
changed=0
while IFS= read -r line || [[ -n "$line" ]]; do
  entry=$line
  if [[ -n "$entry" && "$entry" != \#* && "$entry" != \!* ]]; then
    cert="$source_dir/$entry"
    [[ -f "$cert" ]] || die "configured certificate is missing: $cert"
    details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) \
      || die "cannot inspect configured certificate: $cert"
    serial=$(normalize_serial "${details#*serial=}")
    serial=${serial%%$'\n'*}
    subject=${details#*$'\n'}
    subject=${subject,,}
    if [[ -n ${blocked[$serial]+yes} || "$subject" == *emsign* || "$subject" == *emudhra* ]]; then
      printf '!%s\n' "$entry" >> "$tmp"
      changed=1
      echo "emsign-trust: disabling $entry (serial=$serial)" >&2
      continue
    fi
  fi
  printf '%s\n' "$line" >> "$tmp"
done < "$config"

if (( changed )); then
  if [[ -z "$root" ]]; then
    install -o root -g root -m 0644 "$tmp" "$config"
  else
    install -m 0644 "$tmp" "$config"
  fi
fi

# Debian includes local *.crt files outside ca-certificates.conf. Quarantine
# only matching files by extension, retaining their bytes for recovery.
if [[ -d "$local_dir" ]]; then
  while IFS= read -r -d '' cert; do
    details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) \
      || die "cannot inspect local CA certificate: $cert"
    serial=$(normalize_serial "${details#*serial=}")
    serial=${serial%%$'\n'*}
    subject=${details#*$'\n'}
    subject=${subject,,}
    if [[ -n ${blocked[$serial]+yes} || "$subject" == *emsign* || "$subject" == *emudhra* ]]; then
      mv -- "$cert" "${cert}.emsign-distrusted" || die "cannot quarantine $cert"
      echo "emsign-trust: quarantined local CA $cert (serial=$serial)" >&2
    fi
  done < <(find "$local_dir" -type f -name '*.crt' -print0)
fi

update-ca-certificates --fresh
[[ -s "$bundle" ]] || die "generated CA bundle is empty"

# The package configuration is the source of truth for installed roots. This
# guard also ensures no disabled emSign/serial entry remains enabled.
if awk '!/^#/ && !/^!/ && NF { print $0 }' "$config" | while IFS= read -r entry; do
  cert="$source_dir/$entry"
  details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) || exit 2
  serial=$(normalize_serial "${details#*serial=}")
  serial=${serial%%$'\n'*}
  subject=${details#*$'\n'}
  subject=${subject,,}
  [[ -z ${blocked[$serial]+yes} && "$subject" != *emsign* && "$subject" != *emudhra* ]] || exit 1
done; then
  :
else
  die "a blocked certificate remains enabled in $config"
fi

echo "emsign-trust: updated $bundle; non-target roots preserved" >&2

if [[ "${1:-}" == --ca-store-only ]]; then
  exit 0
fi
[[ $# -eq 0 ]] || die "usage: $0 [--ca-store-only]"

# The fixture root is limited to CA database tests; host configuration below
# is only reachable for the real root filesystem.
if [[ -n "$root" ]]; then
  echo "emsign-trust: fixture CA database updated" >&2
  exit 0
fi

# Scope runtime policy to project services; preserve unit commands and EnvFiles.
install -d -m 0755 /usr/local/libexec /etc/emsign/empty-ca-dir
[[ -z "$(find /etc/emsign/empty-ca-dir -mindepth 1 -print -quit)" ]] || die "empty CA directory is not empty"
cat > /usr/local/libexec/emsign-exec <<'EOF'
#!/bin/sh
set -eu
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE" PIP_CERT="$SSL_CERT_FILE"
export SSL_CERT_DIR=/etc/emsign/empty-ca-dir
# Suppress alternate extra roots and CA flags while preserving unrelated flags.
unset NODE_EXTRA_CA_CERTS
case " ${NODE_OPTIONS:-} " in
  *--use-bundled-ca*|*--use-system-ca*) echo 'emsign: conflicting Node CA option' >&2; exit 1;;
esac
export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--use-openssl-ca"
exec "$@"
EOF
chmod 0755 /usr/local/libexec/emsign-exec
cat > /usr/local/libexec/emsign-node <<'EOF'
#!/bin/sh
exec /usr/local/libexec/emsign-exec /usr/bin/node "$@"
EOF
chmod 0755 /usr/local/libexec/emsign-node
python3 - <<'PYINSTALL'
import fnmatch, pathlib, re, subprocess
patterns = ('kartracers*.service', 'aroma*.service', 'aromara-site.service', 'saturn*.service', 'rod-family*.service')
def run(*args):
    return subprocess.check_output(['systemctl', *args], text=True)
names = set()
for args in [('list-unit-files', '--type=service', '--no-legend', '--no-pager'), ('list-units', '--type=service', '--all', '--no-legend', '--no-pager')]:
    for line in run(*args).splitlines():
        fields = line.lstrip('● ').split()
        if fields and any(fnmatch.fnmatchcase(fields[0], p) for p in patterns):
            names.add(fields[0])
plans = []
for name in sorted(names):
    text = run('cat', name)
    commands = {}
    section, own, continued = '', False, ''
    for raw in text.splitlines():
        if raw.startswith('# /'):
            own = raw.endswith('/90-emsign-trust.conf')
        if own or raw.lstrip().startswith(('#', ';')):
            continue
        line = continued + raw.strip()
        if line.endswith('\\'):
            continued = line[:-1] + ' '
            continue
        continued = ''
        if line.startswith('['):
            section = line
        if section != '[Service]' or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key not in ('ExecStart', 'ExecStartPre', 'ExecStartPost', 'ExecReload', 'ExecStop', 'ExecStopPost'):
            continue
        if not value:
            commands[key] = []
        else:
            # '-' preserves failure handling. Other execution prefixes change
            # credentials/argument semantics and require deliberate handling.
            if value.lstrip('-').startswith(('@', ':', '+', '!')):
                raise SystemExit(f'Unsupported execution prefix in {name}: {key}')
            commands.setdefault(key, []).append(value)
    if not commands.get('ExecStart'):
        raise SystemExit(f'No ExecStart found for {name}')
    lines = ['# Generated by emsign-trust-hardening; original EnvFiles retained.', '[Service]']
    for key, values in commands.items():
        lines.append(key + '=')
        for value in values:
            prefix = '-' if value.startswith('-') else ''
            value = value.removeprefix('-')
            if not value.startswith('/usr/local/libexec/emsign-exec '):
                value = '/usr/local/libexec/emsign-exec ' + value
            lines.append(f'{key}={prefix}{value}')
    plans.append((pathlib.Path('/etc/systemd/system') / (name + '.d') / '90-emsign-trust.conf', '\n'.join(lines) + '\n'))
for path, content in plans:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o644)
    print(f'emsign-trust: scoped service policy {path.parent.name}')
PYINSTALL
systemctl daemon-reload
echo "emsign-trust: installed project service policy; restart required" >&2
