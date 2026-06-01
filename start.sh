#!/usr/bin/env bash
# ============================================================
# provider.pdhc — start.sh
# All-Docker service: DB + app via docker-compose.
# IMPORTANT: No kill -9 on ports — docker-compose down handles it.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORTAL_DIR="$SCRIPT_DIR/provider_portal"

export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Detect docker-compose
if command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
elif docker compose version >/dev/null 2>&1; then
    DC="docker compose"
else
    echo "[Provider] ERROR: No docker-compose found."
    exit 1
fi

echo "[Provider] === provider.pdhc starting ==="

# ── 1. Docker check ──────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
    echo "[Provider] ERROR: Docker is not running."
    echo "  Run: bash /usr/local/www/restart_all.sh"
    exit 1
fi
echo "[Provider] Docker OK"

# ── 2. Stop existing (docker-compose down only — no kill -9) ─
echo "[Provider] Stopping existing containers..."
cd "$PORTAL_DIR"
$DC down 2>/dev/null || true

# ── 3. Start services ────────────────────────────────────────
echo "[Provider] Starting services..."
cd "$PORTAL_DIR"
$DC up -d --build

if [ $? -ne 0 ]; then
    echo "[Provider] ERROR: docker-compose up failed."
    exit 1
fi

# ── 4. Health check ──────────────────────────────────────────
echo "[Provider] Waiting for services..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9070/api/v1/health >/dev/null 2>&1; then
        echo "[Provider]   Application is healthy!"
        break
    fi
    [ "$i" -eq 30 ] && echo "[Provider]   WARNING: Health check not passing yet"
    sleep 2
done

echo ""
echo "[Provider] === provider.pdhc is running ==="
echo "  App:      http://localhost:9070"
echo "  Database: localhost:9071"
echo "  Health:   http://localhost:9070/api/v1/health"
echo "  Logs:     cd $PORTAL_DIR && $DC logs -f"
echo "  Stop:     cd $PORTAL_DIR && $DC down"
