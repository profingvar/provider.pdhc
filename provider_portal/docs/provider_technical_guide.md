# Provider Portal — Technical Integration Guide

Version 1.0 | 2026-03-25

---

## 1. Overview

The PDHC Provider Portal is a Flask-based application that enables healthcare provider organisations to receive, process, and respond to service requests from the central PDHC system. Each provider instance runs as an isolated Docker deployment with its own database.

### Architecture

```
                          ┌─────────────────────────────┐
                          │  PDHC Request Gateway       │
   request.pdhc.se        │  (central dispatcher)       │
                          │  Ports: 9060/9061           │
                          └──────────┬──────────────────┘
                                     │
                          dispatches tasks via push/poll
                                     │
                          ┌──────────▼──────────────────┐
   provider1.pdhc.se      │  Provider Portal Instance   │
                          │                             │
                          │  ┌─────────┐  ┌──────────┐  │
                          │  │ Flask   │  │ Postgres │  │
                          │  │ :9070   │  │ :9071    │  │
                          │  └─────────┘  └──────────┘  │
                          └─────────────────────────────┘
```

---

## 2. Authentication

### API Key Model

All API and web access is authenticated via API keys sent in the `X-API-Key` HTTP header (API) or stored in the Flask session (web UI).

```
X-API-Key: YfLOkY0PtmVv0Vu214zlna4D1aOmg4Nv2wo1Fixs4CE
```

### Who issues keys?

**The PDHC system administrator** issues the initial bootstrap key when provisioning a new provider instance. This key is set in the provider's `.env` file as `BOOTSTRAP_API_KEY` and is created automatically on first application start.

The bootstrap key has `read,write` scopes and **must be rotated** after initial setup.

### Key lifecycle

```
  Bootstrap key (from .env, created on first run)
      │
      ▼
  Active key ──── Rotate (POST /api/v1/api-keys/{guid}/rotate)
      │                │
      │                ├─→ Old key: Revoked (immediate)
      │                └─→ New key: Active (returned once)
      │
      ▼
  Revoke (POST /api/v1/api-keys/{guid}/revoke)
      │
      ▼
  Revoked (permanent, cannot be undone)
```

### Key storage

- Keys are **bcrypt-hashed** at rest — the database never stores plaintext
- The raw key is returned **exactly once** at creation or rotation
- Optional expiry is enforced on every authenticated request
- Revocation is immediate and audit-logged

### Scopes

| Scope   | Permissions                                                |
|---------|------------------------------------------------------------|
| `read`  | View tasks, care plan details, receipts, audit log         |
| `write` | Accept tasks, submit reports, create/rotate/revoke API keys|

---

## 3. API Reference

**Base URL**: `https://provider1.pdhc.se/api/v1`

All endpoints require `X-API-Key` header unless noted. All responses are JSON.

### Health Check

```
GET /api/v1/health
```

No authentication required. Returns:

```json
{
  "status": "ok",
  "database": "connected"
}
```

Status `degraded` with HTTP 503 if the database is unreachable.

---

### Provider Tasks

#### List my tasks

```
GET /api/v1/provider-tasks/my?status=dispatched&limit=50
```

**Scope**: `read`

| Parameter | Type   | Default | Description          |
|-----------|--------|---------|----------------------|
| `status`  | string | —       | Filter by status     |
| `limit`   | int    | 50      | Maximum results      |

#### Get single task

```
GET /api/v1/provider-tasks/{receipt_token}
```

**Scope**: `read`

**Response**:

```json
{
  "guid": "uuid",
  "receipt_token": "string",
  "provider_guid": "uuid",
  "status": "dispatched|acknowledged|in_progress|completed|cancelled",
  "patient_guid": "uuid|null",
  "patient_name": "string|null",
  "careplan_guid": "uuid|null",
  "careplan_title": "string|null",
  "dispatched_at": "ISO-8601",
  "due_at": "ISO-8601|null",
  "acknowledged_at": "ISO-8601|null",
  "completed_at": "ISO-8601|null",
  "notes": "string|null",
  "created_at": "ISO-8601"
}
```

#### Accept task

```
POST /api/v1/provider-tasks/{receipt_token}/accept
Content-Type: application/json

{
  "notes": "Will complete by Friday"
}
```

**Scope**: `write` | Idempotent

#### Get care plan details

```
GET /api/v1/provider-tasks/{receipt_token}/careplan-details
```

**Scope**: `read`

Returns the care plan structure with expected observations (transaction GUIDs, concept names, response types, value sets).

#### Submit report

```
POST /api/v1/provider-tasks/{receipt_token}/report
Content-Type: application/json

{
  "provider_payload": {
    "observations": [
      {
        "transaction_guid": "uuid",
        "concept_guid": "uuid",
        "value": "120",
        "unit": "mmHg",
        "notes": "Measured at rest",
        "recorded_at": "2026-03-25T10:00:00Z"
      }
    ]
  },
  "notes": "Patient in good condition",
  "receipt_message": "Visit completed"
}
```

**Scope**: `write` | Idempotent (same payload hash returns existing receipt)

For **manual mode**, `provider_payload` can be any JSON object without the `observations` key.

For **guided mode**, the `observations` array must include all required transactions from the care plan. A 422 response with validation details is returned if observations are missing or invalid.

---

### Receipts

```
GET /api/v1/provider-receipts?receipt_token=xxx&limit=50
```

**Scope**: `read`

---

### Audit Log

```
GET /api/v1/audit-log?receipt_token=xxx&limit=50
GET /api/v1/audit-log/{guid}
```

**Scope**: `read`

---

### API Key Management

#### Create key

```
POST /api/v1/api-keys
Content-Type: application/json

{
  "scopes": "read,write",
  "label": "integration-service",
  "expires_in_days": 90
}
```

**Scope**: `write`

**Response 201**:

```json
{
  "guid": "uuid",
  "key": "raw-key-shown-once",
  "scopes": "read,write",
  "label": "integration-service",
  "expires_at": "2026-06-23T00:00:00Z",
  "message": "Store this key securely. It will not be shown again."
}
```

#### Rotate key

```
POST /api/v1/api-keys/{guid}/rotate
```

**Scope**: `write` — Revokes old key, issues new one with same scopes.

#### Revoke key

```
POST /api/v1/api-keys/{guid}/revoke
```

**Scope**: `write` — Immediate and permanent.

---

## 4. Error Handling

All errors return a consistent JSON structure:

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable description",
  "details": []
}
```

| HTTP | Code                  | Meaning                                   |
|------|-----------------------|-------------------------------------------|
| 400  | VALIDATION_ERROR      | Invalid input or payload                  |
| 401  | AUTH_MISSING           | No X-API-Key header                       |
| 401  | AUTH_INVALID           | Key not found, expired, or revoked        |
| 403  | AUTH_SCOPE_MISMATCH    | Valid key but lacks required scope        |
| 404  | TASK_NOT_FOUND         | Task or resource does not exist           |
| 409  | CONFLICT               | Duplicate or conflicting action           |
| 422  | VALIDATION_ERROR       | Guided observation validation failure     |
| 500  | INTERNAL_ERROR         | Server-side processing failure            |

### Guided validation errors (422)

When guided observations fail validation, `details` lists each problem:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Observation validation failed",
  "details": [
    {
      "transaction_guid": "uuid",
      "concept_name": "Blood Pressure",
      "message": "Required observation missing"
    }
  ]
}
```

---

## 5. Security Model

### Provider isolation

Each API key is bound to a single provider organisation. A provider can only access tasks, receipts, and audit entries belonging to their own `provider_guid`. Cross-provider access is blocked at the service layer.

### Transport security

- All traffic is encrypted via TLS (HTTPS only — HTTP redirects to HTTPS)
- SSL certificates are managed via Let's Encrypt with automatic renewal

### Data at rest

- API keys: bcrypt-hashed (plaintext never stored)
- All records identified by GUIDs (UUIDs) — no sequential IDs exposed

### Audit trail

Every authenticated action is logged in the audit table with:
- Timestamp
- Provider GUID
- Action type
- Receipt token (where applicable)
- Payload snapshot

---

## 6. Integration Patterns

### Pattern A: Web UI (human users)

1. Provider staff receive API key from PDHC administrator
2. Log in at `https://provider1.pdhc.se`
3. View tasks, accept, review care plans, submit reports via browser

### Pattern B: Machine-to-machine (automated systems)

1. Obtain API key from PDHC administrator
2. Poll `GET /api/v1/provider-tasks/my?status=dispatched` for new tasks
3. Accept tasks via `POST /api/v1/provider-tasks/{token}/accept`
4. Fetch care plan details if guided: `GET /api/v1/provider-tasks/{token}/careplan-details`
5. Submit report: `POST /api/v1/provider-tasks/{token}/report`
6. Verify receipt: `GET /api/v1/provider-receipts?receipt_token={token}`

### Pattern C: Push delivery (subscription)

If configured, the central PDHC gateway pushes tasks to the provider's inbound endpoint:

```
POST /api/v1/inbound/push
```

This eliminates polling — tasks arrive automatically. Push delivery requires:
- `SYNC_ENABLED=true` in provider `.env`
- `REQUEST_SERVICE_URL` pointing to the PDHC gateway
- Provider registered in the gateway's dispatch system

---

## 7. Configuration Reference

Environment variables in `.env`:

| Variable                | Required | Description                                  |
|-------------------------|----------|----------------------------------------------|
| `FLASK_ENV`             | Yes      | `development` or `production`                |
| `SECRET_KEY`            | Yes      | Flask session encryption key                 |
| `DATABASE_URL`          | Yes      | PostgreSQL connection string                 |
| `POSTGRES_USER`         | Yes      | Database username (for Docker)               |
| `POSTGRES_PASSWORD`     | Yes      | Database password (for Docker)               |
| `POSTGRES_DB`           | Yes      | Database name (for Docker)                   |
| `BOOTSTRAP_API_KEY`     | Yes      | Initial API key (first run only)             |
| `BOOTSTRAP_PROVIDER_NAME` | Yes   | Provider display name                        |
| `FLASK_PORT`            | No       | Application port (default: 9070)             |
| `PROVIDER_NAME`         | No       | Human-readable provider name                 |
| `PROVIDER_GUID`         | No       | Fixed GUID for this instance (auto-generated if not set) |
| `REQUEST_SERVICE_URL`   | No       | Central gateway URL for sync                 |
| `SYNC_ENABLED`          | No       | Enable automatic task sync (`true`/`false`)  |

---

## 8. Docker Deployment

### Container structure

| Container         | Image             | Port  | Purpose          |
|-------------------|-------------------|-------|------------------|
| `provider1_app`   | provider1-app     | 9070  | Flask application|
| `provider1_db`    | postgres:16-alpine| 9071  | PostgreSQL       |

### Commands

```bash
# Start
cd /usr/local/www/provider.pdhc/provider_portal
docker-compose up -d --build

# Stop
docker-compose down

# View logs
docker-compose logs -f app

# Run migrations
docker exec provider1_app flask db upgrade

# Database shell
docker exec -it provider1_db psql -U provider_portal -d provider_portal_db
```

### Health check

```bash
curl -s https://provider1.pdhc.se/api/v1/health
# {"status":"ok","database":"connected"}
```

---

## 9. Maintenance

| Task                    | Frequency  | Procedure                                     |
|-------------------------|------------|-----------------------------------------------|
| API key rotation        | 90 days    | Rotate via API or request from PDHC admin     |
| Database backup         | Daily      | `pg_dump` from `provider1_db` container       |
| Log review              | Weekly     | Check audit log for anomalies                 |
| SSL certificate renewal | Automatic  | Let's Encrypt certbot handles this            |
| Dependency updates      | Monthly    | Update `requirements.txt`, rebuild container  |
