# provider.pdhc — Progress

## Phase 1 — Foundation

### 1.a Project scaffold
- **Status**: Complete
- Created `provider_portal/` with Flask app structure
- Created venv, installed all dependencies
- Copied `pdhc.css` into `static/css/`
- Created `CLAUDE.md` per Rule 24

### 1.b Docker and database setup
- **Status**: Complete
- `Dockerfile` for Flask app (Python 3.12, gunicorn)
- `docker-compose.yml` with PostgreSQL (port 9071) and Flask (port 9070)
- `.env` with DB credentials, Flask secret, bootstrap API key

### 1.c Database schema
- **Status**: Complete
- Models: Provider, ApiKey, ProviderTask, TaskAuditLog, SubmissionReceipt, CarePlanCache
- All cross-table references use GUIDs (Rule 18)
- API keys stored as bcrypt hashes

### 1.d start.sh
- **Status**: Complete
- Kills ports 9070–9073, activates venv, starts Docker PostgreSQL, runs migrations, starts Flask
- Ctrl+C graceful shutdown

## Phase 2 — Core services

### 2.a ProviderAccessSessionService — 5/5 tests passed
### 2.b ProviderTaskIntakeService — 5/5 tests passed
### 2.c ProviderQueueManagementService — Complete (service layer)
### 2.d TaskAcknowledgementService — 4/4 tests passed

## Phase 3 — CarePlan and completion

### 3.a CarePlanDetailsService — Complete
### 3.b GuidedResponseComposerService — 4/4 tests passed
### 3.c TaskReportSubmissionService — 4/4 tests passed
### 3.d ProviderReceiptService — Complete

## Phase 4 — Error handling, audit, and hardening

### 4.a Error semantics — 7/7 tests passed
### 4.b ProviderAuditTelemetryService — 5/5 tests passed
### 4.c Security hardening — 6/6 tests passed

## Phase 5 — API endpoint test suite and frontend

### 5.a Full endpoint test script — 19/19 tests passed (incl. E2E flow)
### 5.b Frontend (provider portal UI) — Complete

## Phase 6 — Deployment preparation

### 6.a Documentation
- **Status**: Complete
- `docs/api_contract.md` — Full API contract with request/response schemas, error codes, idempotency rules
- `docs/auth_scope_matrix.md` — Endpoint-to-scope mapping, key lifecycle, provider isolation rules, SSO roadmap
- `docs/operational_runbook.md` — Architecture diagram, start/stop procedures, DB operations, key management, monitoring, troubleshooting, reverse proxy notes, maintenance schedule

### 6.b Server preparation
- **Status**: Complete
- `safe_restart.sh` — Production restart script with:
  - Pre-flight checks (Docker, .env, SECRET_KEY, nginx config)
  - Database backup before restart
  - Graceful port cleanup
  - Migration execution
  - Gunicorn daemon with access/error logs
  - Post-start health check
  - nginx graceful reload (Rule 22)
  - Stop mode: `./safe_restart.sh stop`
- `.env.production` — Production template with placeholder values and generation instructions (Rule 23)
- Bootstrap SU user created automatically on first run from `.env`

---

## Phase 7 — Integration with gateway.pdhc and request.pdhc delivery architecture

### 7.a InboundRequest model extensions
- **Status**: Complete
- Added `organisation_guid` (String 36, indexed) and `grant_expires_at` (DateTime) columns
- Alembic migration `a3f9e2b71c04`

### 7.b GatewayReceipt model
- **Status**: Complete
- New model `gateway_receipts` for storing observation receipts pushed from gateway.pdhc
- Fields: receipt_guid, service_request_guid, patient_guid, provider_org_guid, contract_guid, observations_stored, accepted_at, payload_hash
- Registered in models `__init__.py`

### 7.c POST /api/v1/receipts/ingest endpoint
- **Status**: Complete
- New endpoint receives pushed receipts from gateway.pdhc
- Auth via `X-Service-Key` header (GATEWAY_SERVICE_KEY config)
- Deduplication by receipt_guid (returns `action: duplicate` on re-submit)
- Audit log entry on ingestion
- Config: `GATEWAY_SERVICE_KEY` added to Config and TestConfig

### 7.d Push receiver meta.tag extraction
- **Status**: Complete
- Extended `inbound.py` to extract `contract_guid`, `organisation_guid`, `expires_at` from meta.tag
- All extracted values stored on InboundRequest (contract_guid, organisation_guid, grant_expires_at)
- Existing update path also stores the new fields

### 7.e Gateway receipts dashboard
- **Status**: Complete
- Gateway receipt count on dashboard
- New `/gateway-receipts` page with list view
- Nav link "Gateway" added to base.html

### 7.f Tests — 8/8 passed
- `test_gateway_receipts.py`:
  - `TestReceiptIngestEndpoint::test_valid_receipt` — PASSED
  - `TestReceiptIngestEndpoint::test_missing_service_key` — PASSED
  - `TestReceiptIngestEndpoint::test_invalid_service_key` — PASSED
  - `TestReceiptIngestEndpoint::test_missing_required_fields` — PASSED
  - `TestReceiptIngestEndpoint::test_duplicate_receipt` — PASSED
  - `TestReceiptIngestEndpoint::test_audit_log_created` — PASSED
  - `TestPushReceiverMetaTags::test_push_extracts_all_tags` — PASSED
  - `TestPushReceiverMetaTags::test_push_without_optional_tags` — PASSED

### 7.g Documentation updates
- **Status**: Complete
- `docs/api_contract.md` — added inbound/push and receipts/ingest endpoint docs
- `docs/auth_scope_matrix.md` — added push and gateway service key auth rules
- `progress.md` — this section
- `changed_files.md` — updated

---

**Total tests: 90/90 passed**

**All phases (1–7) complete.**
