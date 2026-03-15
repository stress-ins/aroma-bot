#!/bin/bash
# n8n-tunnel.sh — открывает SSH-туннель к n8n UI и открывает браузер
#
# Использование:
#   ./n8n-tunnel.sh
#
# Требования: ~/.ssh/config должен содержать запись 'vps'
# Или отредактируй VPS_HOST ниже

set -e

# ── Конфигурация ──────────────────────────────────────────────────────
VPS_HOST="vps"            # имя из ~/.ssh/config ИЛИ user@ip
LOCAL_PORT="5678"         # порт на твоей машине
REMOTE_PORT="5678"        # порт n8n на VPS
N8N_URL="http://localhost:${LOCAL_PORT}"
# ─────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${GREEN}🔌 n8n SSH Tunnel${NC}"
echo "──────────────────────────"

# Проверить не занят ли порт уже
if lsof -Pi :${LOCAL_PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Порт ${LOCAL_PORT} уже занят — туннель уже открыт${NC}"
    echo -e "   Открываю ${N8N_URL} ..."
    open "${N8N_URL}" 2>/dev/null || xdg-open "${N8N_URL}" 2>/dev/null || true
    exit 0
fi

echo -e "   VPS: ${YELLOW}${VPS_HOST}${NC}"
echo -e "   Туннель: localhost:${LOCAL_PORT} → remote:${REMOTE_PORT}"
echo ""

# Открыть туннель в фоне
ssh -f -N \
    -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    "${VPS_HOST}"

echo -e "${GREEN}✅ Туннель открыт${NC}"

# Подождать пока n8n ответит
echo -n "   Жду n8n"
for i in $(seq 1 15); do
    if curl -s --max-time 1 "${N8N_URL}" >/dev/null 2>&1; then
        echo -e " ${GREEN}готов!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Открыть браузер
echo -e "   Открываю ${YELLOW}${N8N_URL}${NC}"
open "${N8N_URL}" 2>/dev/null || \
    xdg-open "${N8N_URL}" 2>/dev/null || \
    echo "   Открой вручную: ${N8N_URL}"

echo ""
echo -e "${YELLOW}   [Ctrl+C для закрытия туннеля]${NC}"
echo ""

trap "echo ''; echo -e '${RED}🔌 Туннель закрыт${NC}'; \
    pkill -f 'ssh.*${LOCAL_PORT}:localhost:${REMOTE_PORT}' 2>/dev/null; \
    exit 0" INT

while true; do sleep 60; done
