# Provider Portal — Operational Runbook

## Architecture

```
┌──────────────────────────────────────────┐
│  macmini (production server)             │
│                                          │
│  ┌─────────────┐    ┌─────────────────┐  │
│  │ Reverse     │    │ provider_portal  │  │
│  │ Proxy       │───▶│ Flask :9070     │  │
│  │             │    └────────┬────────┘  │
│  └─────────────┘             │           │
│                    ┌─────────▼────────┐  │
│                    │ PostgreSQL :9071  │  │
│                    │ (Docker)         │  │
│                    └──────────────────┘  │
└──────────────────────────────────────────┘
```

Ports: 9070 (Flask), 9071 (PostgreSQL), 9072–9073 (reserved).

---

## Starting the Application

### Development (local Mac)

```bash
cd /path/to/provider.pdhc
./start.sh
```

This will:
1. Kill any processes on ports 9070–9073
2. Start Docker if not running
3. Create/activate Python venv
4. Install dependencies
5. Start PostgreSQL container
6. Run database migrations
7. Start Flask dev server
8. Ctrl+C for graceful shutdown

### Production (macmini)

```bash
cd /path/to/provider.pdhc
./safe_restart.sh
```

---

## Stopping the Application

### Development
Press `Ctrl+C` — the start.sh trap handler will:
- Stop Flask
- Stop Docker containers
- Deactivate venv

### Production
```bash
./safe_restart.sh stop
```

---

## Database Operations

### Run migrations
```bash
cd provider_portal
source venv/bin/activate
export FLASK_APP=app
flask db migrate -m "Description of change"
flask db upgrade
```

### Connect to database
```bash
docker compose exec db psql -U provider_portal -d provider_portal_db
```

### Backup database
```bash
docker compose exec -T db pg_dump -U provider_portal provider_portal_db > backup_$(date +%Y%m%dT%H%M%S).sql
```

### Restore database
```bash
cat backup_file.sql | docker compose exec -T db psql -U provider_portal -d provider_portal_db
```

---

## API Key Management

### Bootstrap key
Set in `.env` as `BOOTSTRAP_API_KEY`. Created automatically on first run. **Must be rotated in production.**

### Create a new key
```bash
curl -X POST http://localhost:9070/api/v1/api-keys \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"scopes": "read,write", "label": "provider-xyz", "expires_in_days": 90}'
```

### Rotate a key
```bash
curl -X POST http://localhost:9070/api/v1/api-keys/<key-guid>/rotate \
  -H "X-API-Key: <admin-key>"
```

### Revoke a key
```bash
curl -X POST http://localhost:9070/api/v1/api-keys/<key-guid>/revoke \
  -H "X-API-Key: <admin-key>"
```

---

## Monitoring

### Health check
```bash
curl -s http://localhost:9070/ | head -1
# Should return HTML
```

### Check database
```bash
docker compose exec -T db pg_isready -U provider_portal
```

### Check audit log
```bash
curl -s http://localhost:9070/api/v1/audit-log?limit=10 \
  -H "X-API-Key: <key>" | python3 -m json.tool
```

### View logs
```bash
# Flask logs
docker compose logs app

# PostgreSQL logs
docker compose logs db
```

---

## Troubleshooting

### Port already in use
```bash
lsof -ti :9070 | xargs kill -9
lsof -ti :9071 | xargs kill -9
```

### Database connection refused
1. Check Docker is running: `docker info`
2. Check container: `docker compose ps`
3. Check port: `lsof -i :9071`
4. Restart DB: `docker compose restart db`

### Migration errors
```bash
# Check current migration state
flask db current

# If migrations are out of sync, stamp to current
flask db stamp head

# Then create new migration
flask db migrate -m "fix"
flask db upgrade
```

### API key issues
- 401 AUTH_MISSING: no X-API-Key header sent
- 401 AUTH_INVALID: key doesn't match any stored hash, or key expired/revoked
- 403 AUTH_SCOPE_MISMATCH: key valid but lacks required scope

---

## Reverse Proxy Notes (Rule 22)

The production server hosts other services behind its reverse proxy. When configuring:

1. **Use a unique location path** (e.g., `/provider-portal/`) to avoid conflicts
2. **Do not modify** the existing reverse proxy config for other services
3. **Test the proxy config** with `nginx -t` before reloading
4. **Preserve existing upstream blocks** — add a new one for provider_portal
5. **Use safe_restart.sh** which validates the proxy config before restart

Example nginx upstream (do not apply without operator review):
```nginx
upstream provider_portal {
    server 127.0.0.1:9070;
}

location /provider-portal/ {
    proxy_pass http://provider_portal/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## Maintenance Schedule

| Task                    | Frequency  | Command/Action                              |
|-------------------------|------------|---------------------------------------------|
| Database backup         | Daily      | `pg_dump` to backup location                |
| API key audit           | Monthly    | Review active keys, revoke unused            |
| Key rotation            | 90 days    | Rotate all provider keys                     |
| Log review              | Weekly     | Check audit log for anomalies                |
| Dependency update       | Monthly    | `pip list --outdated`, update requirements   |
| Docker image update     | Monthly    | `docker compose pull`, rebuild               |
