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
    [[ $(grep -c -- "-----BEGIN CERTIFICATE-----" "$cert") -eq 1 && $(grep -c -- "-----END CERTIFICATE-----" "$cert") -eq 1 ]] || die "CA file must contain exactly one PEM certificate: $cert"
    details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) \
      || die "cannot inspect configured certificate: $cert"
    serial=${details%%$'\n'*}
    serial=$(normalize_serial "${serial#serial=}")
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
    [[ $(grep -c -- "-----BEGIN CERTIFICATE-----" "$cert") -eq 1 && $(grep -c -- "-----END CERTIFICATE-----" "$cert") -eq 1 ]] || die "CA file must contain exactly one PEM certificate: $cert"
    details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) \
      || die "cannot inspect local CA certificate: $cert"
    serial=${details%%$'\n'*}
    serial=$(normalize_serial "${serial#serial=}")
    subject=${details#*$'\n'}
    subject=${subject,,}
    if [[ -n ${blocked[$serial]+yes} || "$subject" == *emsign* || "$subject" == *emudhra* ]]; then
      mv -- "$cert" "${cert}.emsign-distrusted" || die "cannot quarantine $cert"
      echo "emsign-trust: quarantined local CA $cert (serial=$serial)" >&2
    fi
  done < <(find -L "$local_dir" -type f -name '*.crt' -print0)
fi

update-ca-certificates --fresh
[[ -s "$bundle" ]] || die "generated CA bundle is empty"

# The package configuration is the source of truth for installed roots. This
# guard also ensures no disabled emSign/serial entry remains enabled.
if awk '!/^#/ && !/^!/ && NF { print $0 }' "$config" | while IFS= read -r entry; do
  cert="$source_dir/$entry"
  details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) || exit 2
  serial=${details%%$'\n'*}
  serial=$(normalize_serial "${serial#serial=}")
  subject=${details#*$'\n'}
  subject=${subject,,}
  [[ -z ${blocked[$serial]+yes} && "$subject" != *emsign* && "$subject" != *emudhra* ]] || exit 1
done; then
  :
else
  die "a blocked certificate remains enabled in $config"
fi

# The generated bundle is the final security boundary: inspect every PEM,
# including local/symlinked sources outside ca-certificates.conf.
verify_dir=$(mktemp -d)
awk -v dir="$verify_dir" '
  /-----BEGIN CERTIFICATE-----/ { n++; file=sprintf("%s/%06d.pem",dir,n) }
  file { print > file }
  /-----END CERTIFICATE-----/ { close(file); file="" }
  END { if (file != "" || n == 0) exit 1 }
' "$bundle" || { rm -rf "$verify_dir"; die "malformed generated CA bundle"; }
for cert in "$verify_dir"/*.pem; do
  details=$(openssl x509 -in "$cert" -noout -serial -subject 2>/dev/null) || { rm -rf "$verify_dir"; die "invalid certificate in generated bundle"; }
  serial=${details%%$'\n'*}
  serial=$(normalize_serial "${serial#serial=}")
  subject=${details#*$'\n'}
  subject=${subject,,}
  if [[ -n ${blocked[$serial]+yes} || "$subject" == *emsign* || "$subject" == *emudhra* ]]; then
    rm -rf "$verify_dir"
    die "blocked certificate remains in generated bundle (serial=$serial)"
  fi
done
rm -rf "$verify_dir"
echo "emsign-trust: verified $bundle; non-target roots preserved" >&2

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
# Extra roots need separate sanitization; fail explicitly instead of silently
# discarding private/corporate trust or accepting an unchecked alternate bundle.
if [ -n "${NODE_EXTRA_CA_CERTS:-}" ]; then
  echo "emsign: NODE_EXTRA_CA_CERTS requires an audited clean bundle before service start: $NODE_EXTRA_CA_CERTS" >&2
  exit 1
fi
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
import fnmatch, pathlib, re, shutil, subprocess
patterns = ('kartracers*.service', 'aroma*.service', 'aromara-site.service', 'saturn*.service', 'rod-family*.service')
def run(*args):
    return subprocess.check_output(['systemctl', *args], text=True)
names = set()
for args in [('list-unit-files', '--type=service', '--no-legend', '--no-pager'), ('list-units', '--type=service', '--all', '--no-legend', '--no-pager')]:
    for line in run(*args).splitlines():
        fields = line.lstrip('● ').split()
        if fields and any(fnmatch.fnmatchcase(fields[0], p) for p in patterns):
            names.add(fields[0])
paths, obsolete = set(), set()
for name in sorted(names):
    for line in run('cat', name).splitlines():
        if not line.startswith('# /'):
            continue
        path = pathlib.Path(line[2:])
        if path.name == '90-emsign-trust.conf':
            obsolete.add(path)
        elif path.suffix == '.service' or path.parent.name.endswith('.service.d'):
            # Only project unit definitions may be changed. Shared global
            # service.d configuration and app checkout symlinks are rejected.
            # Resource-only generated drop-ins need no command migration.
            # Ignore them before evaluating write authorization.
            if not re.search(r'^\s*Exec(?:Start|Stop|Reload)', path.read_text(), re.M):
                continue
            owner = path.name if path.suffix == '.service' else path.parent.name[:-2]
            if not any(fnmatch.fnmatchcase(owner, p) for p in patterns):
                if re.search(r'^Exec(?:Start|Stop|Reload)', path.read_text(), re.M):
                    raise SystemExit(f'Exec directive in shared unit config requires review: {path}')
                continue
            allowed = ('/etc/systemd/system/', '/run/systemd/system/', '/usr/lib/systemd/system/', '/lib/systemd/system/')
            target = path.resolve()
            known_project = pathlib.Path('/opt/kartracers-site/deploy/systemd')
            project_link = (path.suffix == '.service' and target.parent == known_project
                            and target.name == path.name and path.name.startswith('kartracers-'))
            if not str(target).startswith(allowed) and not project_link:
                raise SystemExit(f'Refusing to edit unit source outside systemd config: {path}')
            paths.add(path)
plans = []
for path in sorted(paths):
    text = path.read_text()
    section = ''
    lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('['):
            section = stripped
        match = re.match(r'^(\s*Exec(?:Start(?:Pre|Post)?|Reload|Stop(?:Post)?)\s*=)(.*?)(\r?\n)?$', line)
        if section == '[Service]' and match and match[2].strip():
            command = match[2].lstrip()
            prefixes = re.match(r'^[-+!:|@]*', command)[0]
            if '@' in prefixes:
                raise SystemExit(f'Custom argv[0] execution requires manual review: {path}')
            command = command[len(prefixes):]
            if not command.startswith('/usr/local/libexec/emsign-exec '):
                command = '/usr/local/libexec/emsign-exec ' + command
            line = match[1] + prefixes + command + (match[3] or '')
        lines.append(line)
    plans.append((path, ''.join(lines)))
# Update the original directives rather than pinning old commands in an
# override. Future installers ship wrapped unit definitions with fresh args.
for path, content in plans:
    if path.read_text() != content:
        target = path.resolve()
        backup = target.with_name(target.name + '.emsign-before')
        if backup.is_symlink():
            raise SystemExit(f'Refusing symlink backup path: {backup}')
        if not backup.exists():
            shutil.copy2(target, backup)
        path.write_text(content)
        print(f'emsign-trust: migrated unit commands {path}')
for path in obsolete:
    path.unlink(missing_ok=True)
    print(f'emsign-trust: removed obsolete command snapshot {path}')

PYINSTALL
systemctl daemon-reload
echo "emsign-trust: installed project service policy; restart required" >&2
