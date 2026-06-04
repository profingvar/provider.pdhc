#!/usr/bin/env bash
# safe_restart.sh — Safe restart for provider_portal on production (macmini)
# Usage: ./safe_restart.sh [stop]
# Rule 19: operator runs this script on the web instance
# Rule 22: takes precaution to prevent disturbance of other reverse proxy services
set -e

# Step-tracked failure logging — set -e exits on the first error
# but says nothing about *what* failed; the trap below logs the
# step that was active so the operator doesn't have to guess.
# Ticket #236.
CURRENT_STEP="(initialising)"
_on_exit() {
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo >&2
        echo "[safe_restart] FAILED at step: ${CURRENT_STEP} (exit $rc)" >&2
        echo "[safe_restart] Service may be in DEGRADED state — verify gunicorn + DB before walking away." >&2
    fi
}
trap _on_exit EXIT

PORTS=(9070 9071 9072 9073)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$PROJECT_DIR/provider_portal"
VENV_DIR="$APP_DIR/venv"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H-%M-%SZ")

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[safe_restart]${NC} $1"; }
warn() { echo -e "${YELLOW}[safe_restart]${NC} $1"; }
err()  { echo -e "${RED}[safe_restart]${NC} $1" >&2; }

# --- Stop mode ---
CURRENT_STEP='stop mode (--stop flag)'
if [ "${1:-}" = "stop" ]; then
    log "Stopping provider_portal..."
    cd "$APP_DIR"
    docker compose down 2>/dev/null || true
    for port in "${PORTS[@]}"; do
        lsof -ti :"$port" 2>/dev/null | xargs kill 2>/dev/null || true
    done
    log "Stopped."
    exit 0
fi

# --- Pre-flight checks ---
CURRENT_STEP='pre-flight checks (docker / .env / SECRET_KEY / nginx config)'
log "Pre-flight checks..."

# Check Docker is running
if ! docker info >/dev/null 2>&1; then
    err "Docker is not running. Start Docker first."
    exit 1
fi

# Check .env exists
if [ ! -f "$APP_DIR/.env" ]; then
    err ".env file not found at $APP_DIR/.env"
    exit 1
fi

# Check SECRET_KEY is not default
SECRET=$(grep -E "^SECRET_KEY=" "$APP_DIR/.env" | cut -d= -f2-)
if [ "$SECRET" = "change-me-in-production" ] || [ -z "$SECRET" ]; then
    err "SECRET_KEY in .env is not set for production. Generate one:"
    err "  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
    exit 1
fi

# Check BOOTSTRAP_API_KEY is not default
BKEY=$(grep -E "^BOOTSTRAP_API_KEY=" "$APP_DIR/.env" | cut -d= -f2-)
if [ "$BKEY" = "dev-bootstrap-key-change-in-production" ]; then
    warn "BOOTSTRAP_API_KEY is still the default dev value. Change it for production."
fi

# Check nginx config if nginx is present (Rule 22)
if command -v nginx >/dev/null 2>&1; then
    log "Validating nginx configuration..."
    if ! nginx -t 2>/dev/null; then
        err "nginx configuration test failed. Fix before restarting."
        exit 1
    fi
    log "nginx config OK."
fi

# --- Backup database before restart ---
CURRENT_STEP='database backup'
log "Backing up database..."
mkdir -p "$BACKUP_DIR"
cd "$APP_DIR"
if docker compose ps db --status running 2>/dev/null | grep -q running; then
    docker compose exec -T db pg_dump -U "${POSTGRES_USER:-provider_portal}" "${POSTGRES_DB:-provider_portal_db}" \
        > "$BACKUP_DIR/db_backup_${TIMESTAMP}.sql" 2>/dev/null && \
        log "Backup saved: $BACKUP_DIR/db_backup_${TIMESTAMP}.sql" || \
        warn "Backup failed — continuing anyway (database may be empty on first run)"
else
    warn "Database not running — skipping backup"
fi

# --- Gracefully stop existing services ---
CURRENT_STEP='stop existing services'
log "Stopping existing services..."
for port in "${PORTS[@]}"; do
    PID=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$PID" ]; then
        log "  Stopping PID $PID on port $port..."
        kill "$PID" 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
done
docker compose down 2>/dev/null || true

# --- Setup venv ---
CURRENT_STEP='setup venv + pip install'
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

log "Installing dependencies..."
pip install -q -r "$APP_DIR/requirements.txt"

# --- Start database ---
CURRENT_STEP='start database container + wait for ready'
log "Starting PostgreSQL on port 9071..."
cd "$APP_DIR"
docker compose up -d db

log "Waiting for PostgreSQL..."
RETRIES=30
while [ $RETRIES -gt 0 ]; do
    if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-provider_portal}" >/dev/null 2>&1; then
        break
    fi
    RETRIES=$((RETRIES - 1))
    sleep 1
done
if [ $RETRIES -eq 0 ]; then
    err "PostgreSQL did not start within 30 seconds."
    exit 1
fi
log "PostgreSQL is ready."

# --- Run migrations ---
CURRENT_STEP='flask db upgrade'
export FLASK_APP=app
if [ ! -d "migrations/versions" ]; then
    log "Initializing migrations..."
    flask db init
    flask db migrate -m "Initial migration"
fi
log "Running migrations..."
flask db upgrade

# --- Start application ---
CURRENT_STEP='start gunicorn'
log "Starting provider_portal on port 9070..."
gunicorn --bind 0.0.0.0:9070 --workers 2 --timeout 120 "app:create_app()" \
    --access-logfile "$PROJECT_DIR/logs/access.log" \
    --error-logfile "$PROJECT_DIR/logs/error.log" \
    --daemon \
    --pid "$PROJECT_DIR/provider_portal.pid"

# Create logs dir if needed
mkdir -p "$PROJECT_DIR/logs"

# --- Verify ---
CURRENT_STEP='verify gunicorn responds'
sleep 2
if curl -sf http://localhost:9070/ >/dev/null 2>&1; then
    log "Provider Portal is running at http://localhost:9070"
else
    err "Provider Portal failed to start. Check logs at $PROJECT_DIR/logs/"
    exit 1
fi

# --- Reload nginx if present (Rule 22) ---
CURRENT_STEP='nginx reload'
if command -v nginx >/dev/null 2>&1; then
    log "Reloading nginx (graceful)..."
    nginx -s reload 2>/dev/null || warn "nginx reload failed — may need manual reload"
fi

log "Safe restart complete."
log "  App:  http://localhost:9070"
log "  DB:   localhost:9071"
log "  Logs: $PROJECT_DIR/logs/"
log "  PID:  $PROJECT_DIR/provider_portal.pid"
