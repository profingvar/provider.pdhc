# provider.pdhc — Deployment Plan

Standalone Flask + PostgreSQL provider portal.
Ports: 9070 (Flask), 9071 (PostgreSQL), 9072–9073 reserved.
App folder: `provider_portal/`
FHIR 5 compliant. Dockerized. SSO integration (sso.pdhc.se) deferred.

---

## Phase 1 — Foundation

### 1.a Project scaffold
- Create `provider_portal/` with Flask app structure
- Create venv inside `provider_portal/venv/`
- Create `requirements.txt`
- Create `CLAUDE.md` referencing `../css_instrux/repo_css.md`
- Copy `pdhc.css` into `provider_portal/static/css/`

### 1.b Docker and database setup
- `Dockerfile` for Flask app
- `docker-compose.yml` with PostgreSQL (port 9071) and Flask (port 9070)
- `.env` file with DB credentials, Flask secret, bootstrap API key
- PostgreSQL schema migration (Flask-Migrate / Alembic)

### 1.c Database schema
- `providers` — provider identity, API key hash, scopes, created/updated
- `api_keys` — key hash, provider_guid, scopes, expiry, revoked flag, rotation metadata
- `provider_tasks` — receipt_token, provider_guid, status, patient/careplan summary, dispatch metadata, timestamps
- `task_audit_log` — action (acknowledge/report/sync), actor_guid, receipt_token, payload snapshot, timestamp
- `submission_receipts` — receipt_token, status, message, provider_payload hash, submitted_at
- `careplan_cache` — receipt_token, careplan_json, fetched_at, ttl
- All cross-table references use GUIDs (Rule 18)

### 1.d start.sh
- Kill processes on ports 9070–9073
- Activate venv
- Start Docker (PostgreSQL) if not running
- Start Flask app
- Ctrl+C graceful shutdown and deactivate

---

## Phase 2 — Core services

### 2.a ProviderAccessSessionService
- API key validation middleware (`X-API-Key` header)
- Provider session context initialization
- Key scope enforcement (read/write separation)
- Tests: valid key, missing key (401), invalid key (401), scope mismatch (403)

### 2.b ProviderTaskIntakeService
- `GET /api/v1/provider-tasks/{receipt_token}` — fetch single task
- `GET /api/v1/provider-tasks/my?status=...&limit=...` — list provider tasks
- Merge remote state with local DB representation
- Tests: fetch by token, list with filters, 404 on missing token, auth enforcement

### 2.c ProviderQueueManagementService
- Local task cache in PostgreSQL
- Mark task as active
- Toggle active-only vs full queue view
- Clear local queue
- Reconciliation policy: server state is authoritative
- Tests: cache CRUD, active toggle, reconciliation after external status change

### 2.d TaskAcknowledgementService
- `POST /api/v1/provider-tasks/{receipt_token}/accept`
- Validate selected task/token
- Optional notes
- Idempotency: re-acknowledge same task returns same result (409 if conflicting)
- Audit log entry on acknowledge
- Tests: acknowledge, duplicate acknowledge (idempotent), invalid token (400), already-completed task (409)

---

## Phase 3 — CarePlan and completion

### 3.a CarePlanDetailsService
- `GET /api/v1/provider-tasks/{receipt_token}/careplan-details`
- Fetch and cache careplan details linked to task
- Return transactions with concept metadata, response types, valueset values, units, required flags
- Tests: fetch details, 404 on missing, cache behavior

### 3.b GuidedResponseComposerService
- Build transaction response inputs from careplan details
- Validate required responses before submission
- Construct normalized observation payload per transaction
- Tests: valid composition, missing required field (422), categorical validation

### 3.c TaskReportSubmissionService
- `POST /api/v1/provider-tasks/{receipt_token}/report`
- Accept `provider_payload`, optional `notes`, optional `receipt_message`
- Guided mode: validate observations array against careplan requirements
- Manual mode: accept freeform JSON payload
- Idempotency: re-submit same payload returns same receipt
- Audit log entry on submission
- Tests: guided submit, manual submit, missing required observations (422), duplicate submit (409)

### 3.d ProviderReceiptService
- Record submission outcomes (token, status, message, timestamp)
- Query receipts by provider/task
- Receipt tokens map to immutable operation history
- Tests: receipt creation, query, immutability

---

## Phase 4 — Error handling, audit, and hardening

### 4.a Error semantics
- Standardized error response format: `{ "code": "...", "message": "...", "details": [...] }`
- HTTP status mapping per Section 7 of spec (400/401/403/404/409/422/500)
- Guided submission errors identify exact missing/invalid transactions
- Tests: each error code scenario

### 4.b ProviderAuditTelemetryService
- All acknowledge/report actions logged with actor identity and timestamps
- Receipt tokens linked to immutable audit trail
- Tests: audit trail completeness, immutability

### 4.c Security hardening
- API key storage: hashed (bcrypt), rotation support, expiry, revocation
- Minimize sensitive local storage
- Strict origin validation on any cross-window messaging
- Tests: key rotation, expired key rejection, revoked key rejection

---

## Phase 5 — API endpoint test suite and integration

### 5.a Full endpoint test script
- Script testing all endpoints per capability statement (Rule 9, Rule 20)
- Results stored in `./results/<timestamp>_results/` (Rule 11)

### 5.b Frontend (provider portal UI)
- Templates extending `base.html` per `repo_css.md`
- Provider login (API key entry)
- Task list / queue view
- Task detail + acknowledge
- Guided response form
- Manual submission form
- Receipt history view

### 5.c Integration testing
- End-to-end flow: intake → acknowledge → guided complete → receipt
- Network failure recovery for queue sync
- Cache vs server state reconciliation

---

## Phase 6 — Deployment preparation

### 6.a Documentation
- API contract documentation
- Auth scope matrix
- Operational runbook

### 6.b Server preparation
- `safe_restart.sh` for web instance
- `.env` fully prepared with bootstrap SU user (Rule 23)
- Reverse proxy caution per Rule 22

---

## Phase 7 — Integration with gateway.pdhc and request.pdhc delivery architecture

### 7.a InboundRequest model extensions
- Add `organisation_guid` (String 36, indexed) and `grant_expires_at` (DateTime) columns
- Alembic migration

### 7.b GatewayReceipt model + migration
- New `gateway_receipts` table: receipt_guid, service_request_guid, patient_guid, provider_org_guid, contract_guid, observations_stored, accepted_at, payload_hash

### 7.c POST /api/v1/receipts/ingest endpoint
- Receive pushed receipts from gateway.pdhc
- Auth via `X-Service-Key` header (GATEWAY_SERVICE_KEY)
- Deduplication by receipt_guid
- Audit log on ingestion

### 7.d Push receiver meta.tag extraction
- Extract `contract_guid`, `organisation_guid`, `expires_at` from meta.tag
- Store on InboundRequest

### 7.e Gateway receipts dashboard
- Dashboard card with count
- `/gateway-receipts` list page
- Nav link

### 7.f Tests
- 8 tests: receipt ingest (valid, missing key, invalid key, missing fields, duplicate, audit) + push meta.tag extraction (all tags, optional tags)

### 7.g Documentation
- api_contract.md — inbound/push and receipts/ingest endpoint docs
- auth_scope_matrix.md — push and gateway service key auth rules

---

## API Key Management Rules

- **Storage**: hashed with bcrypt, never stored in plaintext
- **Rotation**: new key generated, old key grace period (configurable), then revoked
- **Expiry**: configurable TTL per key, enforced on every request
- **Revocation**: immediate revocation endpoint, audit logged
- **Bootstrap**: initial SU key seeded from `.env` on first run
- **Future**: SSO integration via sso.pdhc.se
