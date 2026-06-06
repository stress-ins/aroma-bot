#!/usr/bin/env bash
# graphify-bootstrap.sh — idempotent bootstrap для knowledge graph.
#
# Запускается ОДНОКРАТНО после git clone (документировано в CONTRIBUTING.md).
# 1) Активирует tracked .githooks/ через `git config core.hooksPath`
# 2) Если graphify-out/graph.json свежий (< 7 дней) — exit 0 (idempotent)
# 3) Иначе — `graphify ingest .` для построения графа
#
# Повторные запуски на свежем графе — безопасны и быстры (< 1 сек).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

GRAPH_FILE="graphify-out/graph.json"
FRESH_DAYS=7

# Step 1: активировать tracked hooks (idempotent)
CURRENT_HOOKS_PATH="$(git config --get core.hooksPath || echo '')"
if [ "$CURRENT_HOOKS_PATH" != ".githooks" ]; then
    git config core.hooksPath .githooks
    echo "[graphify-bootstrap] core.hooksPath → .githooks"
else
    echo "[graphify-bootstrap] core.hooksPath уже .githooks — skip"
fi

# Step 2: idempotent freshness check
if [ -f "$GRAPH_FILE" ]; then
    if find "$GRAPH_FILE" -mtime -$FRESH_DAYS -print -quit 2>/dev/null | grep -q .; then
        echo "[graphify-bootstrap] graph fresh (< $FRESH_DAYS days) — skip"
        exit 0
    fi
    echo "[graphify-bootstrap] graph stale (≥ $FRESH_DAYS days) — refreshing via graphify update"
else
    echo "[graphify-bootstrap] graph отсутствует — building"
fi

# Step 3: проверить наличие graphify CLI
if ! command -v graphify >/dev/null 2>&1; then
    echo "[graphify-bootstrap] ERROR: graphify CLI не установлен."
    echo "  Установка: pipx install graphify (или см. https://github.com/pkutsenko/graphify)"
    exit 1
fi

# Step 4: построить/обновить граф через `graphify update <path>` (re-extract code, без LLM)
echo "[graphify-bootstrap] graphify update . (~3-5 минут)"
graphify update .

if [ -f "$GRAPH_FILE" ]; then
    SIZE=$(du -h "$GRAPH_FILE" | cut -f1)
    echo "[graphify-bootstrap] DONE — $GRAPH_FILE ($SIZE)"
else
    echo "[graphify-bootstrap] ERROR: update завершился, но $GRAPH_FILE не создан"
    exit 1
fi
