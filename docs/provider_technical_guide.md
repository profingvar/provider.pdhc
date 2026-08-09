# Provider Portal — Technical Integration Guide

> For developers integrating with the PDHC provider delivery system.
> Covers API endpoints, authentication, data formats, and security model.

---

## 1) Architecture overview

```
                    PDHC Platform                         Provider Side
                    ─────────────                         ─────────────

              ┌──────────────────┐
              │  request.pdhc    │
              │  (orchestrator)  │
              └──────┬───────────┘
                     │
           ┌─────────┴──────────┐
           │                    │
      Push delivery        Poll/Subscribe
      (Type 1)             (Type 2)
           │                    │
           ▼                    ▼
    POST /inbound/push    GET /provider/feed  ──►  GET /provider/download/<sr>
           │                    │                          │
           └────────┬───────────┘                          │
                    │                                      │
                    ▼                                      ▼
              ┌──────────────────┐              ┌──────────────────┐
              │  provider.pdhc   │              │  FHIR Bundle     │
              │  (portal)        │              │  + grant_token   │
              └──────┬───────────┘              └──────────────────┘
                     │
                     │  Provider completes work
                     │
                     ▼
              POST /provider/report/<sr>
              (PAT + grant_token)
                     │
                     ▼
              ┌──────────────────┐
              │  gateway.pdhc    │  ◄── validates report, derives org/contract
              │  derives context │      from PAT + grant + SR context
              │  & stores report │
              └──────────────────┘
```

---

## 2) Authentication

### 2.1 Provider Access Token (PAT)

All communication between provider.pdhc and request.pdhc uses a **Provider Access Token**. This replaces the legacy SSO API key.

A PAT is issued by an administrator on the request platform and binds to:
- A specific **provider organisation** (org GUID)
- A specific **contract** (contract GUID)
- Allowed **scopes** (`read`, `write`, or `read,write`)
- A **delivery mode** (`push` or `poll`)

**The PAT determines your identity.** You never pass your organisation GUID as a parameter — it is derived from the token.

### 2.2 Using the PAT

Include the token in every request to request.pdhc:

```http
GET /api/v1/provider/feed
X-Provider-Token: <your-pat-token>
Accept: application/json
```

### 2.3 PAT lifecycle

| Event | What happens |
|-------|-------------|
| **Issued** | Admin creates PAT; raw token shown once, never stored |
| **Active** | Token validates against bcrypt hash; org/contract bound |
| **Expired** | Past `expires_at`; rejected with 401 |
| **Revoked** | Admin revokes; rejected with 401 |

### 2.4 Push secret (Type 1 providers)

If your organisation receives **pushed** deliveries, request.pdhc sends a `X-Push-Secret` header with each push. Your endpoint must validate this header matches the shared secret established during PAT issuance.

### 2.5 Local API keys

The provider portal itself uses **local API keys** (separate from PATs) for its own API and web UI. These are managed via the portal's key management endpoints and stored as bcrypt hashes.

---

## 3) Data flow — Poll mode (Type 2)

### 3.1 Step 1: Fetch the feed

```http
GET /api/v1/provider/feed?since=2026-03-24T00:00:00Z&limit=50
X-Provider-Token: <pat>
```

**Response** (metadata only — no patient data):

```json
{
  "items": [
    {
      "service_request_guid": "sr-abc-123",
      "match_guid": "match-456",
      "status": "pending",
      "title": "Mobility Assessment",
      "intent": "order",
      "priority": "routine",
      "contract_guid": "con-789",
      "created_at": "2026-03-24T10:00:00Z",
      "updated_at": "2026-03-24T10:00:00Z",
      "download_url": "/api/v1/provider/download/sr-abc-123"
    }
  ],
  "total": 1
}
```

> **GDPR data minimization:** The feed contains only operational metadata. No patient names, diagnoses, or clinical data. This reduces exposure if the feed is cached or logged.

### 3.2 Step 2: Download the FHIR Bundle

```http
GET /api/v1/provider/download/sr-abc-123
X-Provider-Token: <pat>
```

**Response:**

```json
{
  "fhir_resource": {
    "resourceType": "ServiceRequest",
    "id": "sr-abc-123",
    "status": "active",
    "intent": "order",
    "priority": "routine",
    "subject": { "reference": "Patient/pat-001", "display": "John Doe" },
    "authoredOn": "2026-03-24T10:00:00Z",
    "occurrencePeriod": {
      "start": "2026-03-24",
      "end": "2026-04-24"
    },
    "contained": [
      {
        "resourceType": "CarePlan",
        "id": "cp-001",
        "title": "Mobility Assessment",
        "goal": [ ... ],
        "activity": [ ... ]
      },
      {
        "resourceType": "Patient",
        "id": "pat-001",
        "name": [{ "given": ["John"], "family": "Doe" }]
      }
    ],
    "basedOn": [
      { "reference": "Contract/con-789" }
    ]
  },
  "grant_token": "a1b2c3d4e5f6...",
  "service_request_guid": "sr-abc-123",
  "patient_guid": "pat-001",
  "contract_guid": "con-789",
  "provider_org_guid": "org-xyz"
}
```

**Important:** Store the `grant_token` — you need it to submit reports back. It is an HMAC-signed composite key that proves the server authorised you to access this specific patient's data.

---

## 4) Data flow — Push mode (Type 1)

### 4.1 Receiving a push

request.pdhc sends a FHIR Bundle to your registered endpoint:

```http
POST /api/v1/inbound/push
X-Push-Secret: <shared-secret>
Content-Type: application/fhir+json

{
  "resourceType": "Bundle",
  "type": "message",
  "meta": {
    "tag": [
      { "system": "https://pdhc.se/delivery", "code": "receipt_token", "display": "rt-abc" },
      { "system": "https://pdhc.se/delivery", "code": "grant_token", "display": "a1b2c3..." }
    ]
  },
  "entry": [
    { "resource": { "resourceType": "ServiceRequest", ... } }
  ]
}
```

### 4.2 Processing the push

1. **Validate** `X-Push-Secret` matches your configured secret
2. **Extract** `receipt_token` and `grant_token` from `meta.tag`
3. **Extract** the `ServiceRequest` from `entry[0].resource`
4. **Store** the request, care plan, and grant token locally
5. **Return** `202 Accepted`

### 4.3 Acknowledging receipt

After processing, acknowledge the delivery:

```http
POST /api/v1/provider/receipt/rt-abc/ack
X-Provider-Token: <pat>
Content-Type: application/json

{ "status": "acknowledged" }
```

---

## 5) Submitting a report

When the provider has completed the work, submit a **minimal report** to gateway.pdhc. The gateway derives `organisation_guid` from the PAT and `contract_guid` from the grant — providers do not need to send these fields.

```http
POST /api/v1/provider/report/sr-abc-123
X-Provider-Token: <pat>
Content-Type: application/json

{
  "patient_guid": "pat-001",
  "grant_token": "a1b2c3d4e5f6...",
  "status": "completed",
  "report_payload": {
    "observations": [
      {
        "transaction_guid": "tx-001",
        "value": "42",
        "recorded_at": "2026-03-25T14:30:00Z",
        "notes": "Full range of motion restored"
      }
    ]
  }
}
```

**Per observation, send only:**

| Field | Required | Description |
|-------|----------|-------------|
| `transaction_guid` | yes | Links to a transaction in the SR's CarePlan |
| `value` | yes | The measured/observed value |
| `recorded_at` | yes | ISO-8601 timestamp of observation |
| `notes` | no | Free-text note (omit entirely if empty) |

**Do NOT send** `concept_guid` or `unit` — the gateway derives these from the ServiceRequest context (transaction map).

### 5.1 Validation chain (gateway.pdhc)

The gateway validates the report through a 10-step chain:

| Step | What is verified |
|------|-----------------|
| 1. PAT | Token is valid, not expired, not revoked; org_guid derived from token |
| 2. Body org cross-check | If `organisation_guid` is provided in body, must match PAT org (backward compat) |
| 3. Grant validation | Delegated to request.pdhc internal API; returns contract_guid, grant_type |
| 4. Body contract cross-check | If `contract_guid` is provided in body, must match grant's contract (backward compat) |
| 5. SR context | Fetched from request.pdhc internal API; returns transactions, goals, patient_guid |
| 6. Patient cross-check | `patient_guid` in body must match SR subject |
| 7. Observation enrichment | `concept_guid` and `unit` derived from SR transaction map |
| 8. Observation validation | Values validated against transaction definitions |
| 9. Contract scope | Concepts checked against contract return_scope (obligatory/optional) |
| 10. Store & audit | Report stored, audit trail created, receipt returned |

If any check fails, the request is rejected with an appropriate error code and the attempt is audit-logged.

### 5.2 Response

```json
{
  "status": "recorded",
  "service_request_guid": "sr-abc-123",
  "match_status": "completed"
}
```

---

## 6) FHIR ServiceRequest structure

The ServiceRequest is a FHIR R5 envelope containing:

| Field | Content |
|-------|---------|
| `id` | ServiceRequest GUID |
| `status` | `active` |
| `intent` | `order`, `plan`, or `proposal` |
| `priority` | `routine`, `urgent`, `asap`, `stat` |
| `subject` | Reference to contained Patient |
| `authoredOn` | When the request was sent |
| `occurrencePeriod` | Validity period (start/end) |
| `requester` | Who created the request (with organisation extension) |
| `performer` | Receiver organisations |
| `basedOn` | Reference to governing Contract |
| `contained` | Array of: CarePlan, Patient, Goals |

### 6.1 Contained CarePlan

The CarePlan contains the clinical instructions:

```json
{
  "resourceType": "CarePlan",
  "title": "Mobility Assessment",
  "goal": [
    {
      "description": { "text": "Assess range of motion" },
      "target": [
        { "measure": { "text": "Shoulder flexion" }, "detailString": "degrees" }
      ]
    }
  ],
  "activity": [
    {
      "detail": {
        "description": "Measure shoulder flexion bilaterally",
        "status": "not-started"
      }
    }
  ]
}
```

---

## 7) Provider portal API (local)

The provider portal exposes its own API for local integrations (EHR systems, mobile apps).

### 7.1 Authentication

All endpoints require `X-API-Key` header with a local portal API key.

### 7.2 Endpoints

| Method | Path | Scope | Purpose |
|--------|------|-------|---------|
| GET | `/api/v1/provider-tasks/my` | read | List all tasks |
| GET | `/api/v1/provider-tasks/{receipt_token}` | read | Get task detail |
| POST | `/api/v1/provider-tasks/{receipt_token}/accept` | write | Acknowledge task |
| POST | `/api/v1/provider-tasks/{receipt_token}/report` | write | Submit report |
| GET | `/api/v1/provider-tasks/{receipt_token}/careplan-details` | read | Get care plan |
| GET | `/api/v1/provider-receipts` | read | List submission receipts |
| GET | `/api/v1/audit-log` | read | View audit trail |
| POST | `/api/v1/api-keys` | write | Create API key |
| POST | `/api/v1/api-keys/{guid}/revoke` | write | Revoke key |
| POST | `/api/v1/api-keys/{guid}/rotate` | write | Rotate key |
| POST | `/api/v1/inbound/push` | — | Receive push (X-Push-Secret) |
| GET | `/api/v1/health` | — | Health check (no auth) |

### 7.3 Report submission format

```http
POST /api/v1/provider-tasks/{receipt_token}/report
X-API-Key: <local-key>
Content-Type: application/json

{
  "provider_payload": {
    "observations": [
      {
        "transaction_guid": "tx-001",
        "value": "normal",
        "notes": "No abnormalities detected"
      }
    ]
  },
  "notes": "Patient cooperative, assessment complete",
  "receipt_message": "Assessment completed on 2026-03-25"
}
```

Observations are validated against the care plan's transaction definitions when available.

---

## 8) Configuration

### 8.1 Environment variables

```bash
# Instance identity
PROVIDER_GUID=<your-org-guid>          # assigned by PDHC admin
PROVIDER_NAME="Clinic Name"

# Connection to request.pdhc
REQUEST_SERVICE_URL=https://request.pdhc.se/api/v1
PROVIDER_TOKEN=<pat-from-admin>        # Provider Access Token

# Push reception (Type 1 only)
PUSH_SECRET=<shared-secret>            # must match PAT's push_auth_key

# Sync settings (Type 2 — poll)
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=60              # how often to check for new requests

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/provider_db

# Security
SECRET_KEY=<random-string>
BOOTSTRAP_API_KEY=<initial-admin-key>  # used on first run only
```

### 8.2 Legacy configuration (deprecated)

```bash
SSO_API_KEY=<sso-key>                  # replaced by PROVIDER_TOKEN
```

If `PROVIDER_TOKEN` is set, the portal uses PAT-based authentication. If only `SSO_API_KEY` is set, it falls back to legacy mode.

---

## 9) Security model

### 9.1 Defense in depth

```
Layer 1: PAT  ──────────  Authenticates provider org identity (gateway derives org_guid)
Layer 2: Grant token  ───  Validated by request.pdhc; proves authorised exchange; yields contract_guid
Layer 3: SR context  ────  Fetched from request.pdhc; yields transactions, patient, contract
Layer 4: Contract scope ─  Fetched from contract.pdhc; enforces return_scope (obligatory/optional)
Layer 5: Audit trail  ───  Every access logged with patient GUID (GDPR)
```

### 9.2 What each token protects

| Token | Scope | Issued by | Stored where |
|-------|-------|-----------|-------------|
| PAT | Org + contract identity | request.pdhc admin | Provider config (.env) |
| Grant token | Single SR + patient exchange | request.pdhc (auto) | InboundRequest.grant_token |
| Push secret | Mutual auth for push delivery | request.pdhc admin | Provider config (.env) |
| Local API key | Portal access | Portal admin | Portal DB (bcrypt) |

### 9.3 HMAC stays on request.pdhc

The HMAC secret used to compute grant tokens is held **only** by request.pdhc. The gateway never sees or computes HMAC — it delegates grant validation to request.pdhc via an internal service-to-service API call (`POST /internal/grant/validate` with `X-Service-Key`).

### 9.3 Key rotation

- **PAT:** Admin issues new PAT, provider updates `.env`, old PAT revoked
- **Push secret:** Admin issues new PAT with new push_auth_key
- **Local API key:** Use `POST /api-keys/{guid}/rotate` — revokes old, issues new

### 9.4 GDPR compliance

- Feed returns metadata only (no patient data in listing)
- Each bundle download is individually audit-logged with `data_subject_guid`
- Reports logged with patient identifier for subject access requests
- Grant tokens limit data exchange to specific patient + request combinations

---

## 10) Error codes

| HTTP | Code | Meaning |
|------|------|---------|
| 400 | `bad_request` | Missing or invalid fields |
| 400 | `VALIDATION_ERROR` | Observation validation failed (see `details`) |
| 401 | `unauthenticated` | Missing or invalid PAT / API key / push secret |
| 403 | `unauthorized` | Valid token but insufficient scope or org mismatch |
| 404 | `not_found` | Resource does not exist |
| 409 | `CONFLICT` | Task in wrong state for this action |
| 422 | `VALIDATION_ERROR` | Guided response validation failed |
| 502 | `UPSTREAM_ERROR` | request.pdhc unreachable or returned error |

All errors follow the format:

```json
{
  "code": "error_code",
  "message": "Human-readable description"
}
```

---

## 11) Database schema

### 11.1 Core tables

| Table | Purpose |
|-------|---------|
| `providers` | Provider instance identity |
| `api_keys` | Local API keys (bcrypt hashed) |
| `inbound_requests` | Synced requests from request.pdhc |
| `provider_tasks` | Working task queue |
| `submission_receipts` | Report submission outcomes |
| `task_audit_logs` | Audit trail |
| `sync_states` | Sync cursor and status |
| `careplan_caches` | Cached care plan data (1h TTL) |

### 11.2 Key columns on inbound_requests

| Column | Type | Purpose |
|--------|------|---------|
| `request_guid` | String(36) | ServiceRequest GUID from request.pdhc |
| `fhir_resource` | JSON | Full FHIR ServiceRequest envelope |
| `patient_guid` | String(36) | For composite key report submission |
| `contract_guid` | String(36) | For composite key report submission |
| `grant_token` | String(128) | HMAC token for authorised data exchange |
| `careplan_json` | JSON | Extracted CarePlan from FHIR resource |
| `checksum` | String(64) | SHA-256 for change detection |

## Port Allocation

All ports bind to `127.0.0.1` (loopback only); external traffic arrives
via the reverse proxy.

| Port | Service |
|------|---------|
| 9070 | Flask application (Gunicorn) |
| 9071 | PostgreSQL database |
