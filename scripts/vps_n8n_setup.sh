#!/usr/bin/env bash
# One-time VPS setup for n8n Docker service.
# Run: bash /opt/aroma/scripts/vps_n8n_setup.sh
set -euo pipefail

echo "=== n8n VPS Setup ==="

# Install Docker if missing
if ! command -v docker &>/dev/null; then
  apt-get update -qq
  apt-get install -y docker.io
  systemctl enable docker
  systemctl start docker
  echo "Docker installed."
else
  echo "Docker already installed."
fi

# Create n8n data volume
docker volume create n8n_data || true
echo "Volume n8n_data ready."

# Install systemd unit
cp /opt/aroma/deploy/n8n.service /etc/systemd/system/n8n-aroma.service
systemctl daemon-reload
systemctl enable n8n-aroma
systemctl start n8n-aroma

echo ""
echo "=== n8n started as n8n-aroma systemd service ==="
echo "Check status: systemctl status n8n-aroma"
echo "Access via SSH tunnel: ssh -L 5678:127.0.0.1:5678 root@46.32.186.192"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:5678 and set up admin account"
echo "  2. Create API key in n8n UI → Settings → API Keys"
echo "  3. Add N8N_API_KEY and N8N_WEBHOOK_SECRET to GitHub Secrets"
