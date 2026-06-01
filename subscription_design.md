# provider.pdhc — Subscription Design Document

## 1) Problem Statement

The provider portal must subscribe to data from `request.pdhc.se` (the central request registry). When the request service registers new requests in the form of JSON careplans, any request carrying this provider's name/GUID must be automatically downloaded and made available in the portal.

Authentication is via SSO-issued keys from `sso.pdhc.se`.

The same codebase must support multiple independent instances — each configured for a different provider identity (name + GUID).

---

## 2) Architecture Overview

```
┌─────────────────┐         ┌──────────────┐         ┌────────────────────────────┐
│ request.pdhc.se │         │ sso.pdhc.se  │         │ provider.pdhc              │
│                 │         │              │         │                            │
│ Request         │◄──auth──│ SSO Key      │──auth──▶│ Instance: "Lab Karolinska" │
│ Registry        │         │ Store        │         │ GUID: abc-123              │
│                 │         └──────────────┘         │ Port: 9070                 │
│ Stores JSON     │                                  ├────────────────────────────┤
│ careplans       │────pull──────────────────────────▶│ Instance: "Radiology SU"   │
│                 │                                  │ GUID: def-456              │
│                 │                                  │ Port: 9074                 │
└─────────────────┘                                  └────────────────────────────┘
```

**Pull model**: each provider portal instance periodically polls `request.pdhc.se` for new/updated requests matching its provider GUID. No inbound connections required — the portal can run behind firewalls.

---

## 3) Instance Identity Configuration

Each instance is configured via `.env`. The codebase is identical; only the environment differs.

### New .env variables

```env
# --- Instance identity (one provider per instance) ---
PROVIDER_GUID=<guid-assigned-to-this-provider>
PROVIDER_NAME=<human-readable-provider-name>

# --- Upstream request service ---
REQUEST_SERVICE_URL=https://request.pdhc.se/api/v1
SSO_API_KEY=<api-key-issued-by-sso.pdhc.se-for-this-provider>

# --- Sync settings ---
SYNC_INTERVAL_SECONDS=60
SYNC_ENABLED=true
```

### Multi-instance deployment

Each instance runs as a separate Docker stack with its own database, ports, and `.env`:

| Instance            | PROVIDER_GUID | Ports       | Database                  |
|---------------------|---------------|-------------|---------------------------|
| Lab Karolinska      | abc-123...    | 9070, 9071  | provider_portal_lab_db    |
| Radiology SU        | def-456...    | 9074, 9075  | provider_portal_rad_db    |
| Cardiology Centrum  | ghi-789...    | 9078, 9079  | provider_portal_card_db   |

This gives full isolation — no cross-provider data leaks, independent scaling, independent maintenance windows.

---

## 4) New Database Model: InboundRequest

The raw data from `request.pdhc.se` is stored separately from the working `ProviderTask`. This preserves the original request as received and allows re-processing.

### Table: `inbound_requests`

| Column            | Type          | Notes                                          |
|-------------------|---------------|-------------------------------------------------|
| id                | Integer PK    | Internal sequence                               |
| guid              | String(36)    | Local GUID, unique                              |
| request_guid      | String(36)    | GUID from request.pdhc.se (immutable, unique)   |
| provider_guid     | String(36)    | Must match instance PROVIDER_GUID               |
| receipt_token     | String(255)   | Token from request service, links to ProviderTask|
| careplan_json     | JSON          | Full JSON careplan as received                  |
| status            | String(50)    | new → synced → acknowledged → completed         |
| source_url        | String(512)   | The endpoint this was fetched from              |
| checksum          | String(64)    | SHA-256 of careplan_json for change detection   |
| received_at       | DateTime(tz)  | When first downloaded                           |
| last_synced_at    | DateTime(tz)  | When last checked/updated from upstream         |
| created_at        | DateTime(tz)  | Row creation                                    |

### Table: `sync_state`

Tracks the sync cursor so we only fetch new/changed data.

| Column            | Type          | Notes                                          |
|-------------------|---------------|-------------------------------------------------|
| id                | Integer PK    |                                                 |
| provider_guid     | String(36)    | This instance's provider                        |
| last_sync_at      | DateTime(tz)  | Timestamp of last successful sync               |
| last_sync_cursor  | String(255)   | Opaque cursor if the upstream API supports it   |
| requests_synced   | Integer       | Running count of synced requests                |
| last_error        | Text          | Last sync error message (null if OK)            |
| updated_at        | DateTime(tz)  |                                                 |

### Relationship to existing models

```
InboundRequest (raw from request.pdhc.se)
    │
    ├──creates──▶ ProviderTask (working copy for acknowledge/report flow)
    │
    └──stores───▶ CarePlanCache (careplan details for guided response)
```

The `InboundRequest.receipt_token` links to `ProviderTask.receipt_token`.

---

## 5) New Service: RequestSubscriptionService

### Responsibilities

1. Authenticate to `request.pdhc.se` using SSO-issued key
2. Poll for requests matching this instance's `PROVIDER_GUID`
3. Detect new/changed requests (via checksum comparison)
4. Store raw data in `inbound_requests`
5. Create/update `ProviderTask` records from inbound data
6. Cache careplan JSON in `careplan_cache`
7. Log all sync activity in `task_audit_log`
8. Track sync state (cursor, errors, counts)

### Sync flow (detail)

```
1. Read SYNC_ENABLED from config. If false, skip.

2. Read last_sync_at from sync_state table.

3. Call upstream:
   GET {REQUEST_SERVICE_URL}/requests
   Headers:
     X-API-Key: {SSO_API_KEY}
   Query params:
     provider_guid={PROVIDER_GUID}
     since={last_sync_at}          (ISO-8601, if supported by upstream)
     status=active                 (if supported)

4. For each request in the response:

   a. Compute checksum = SHA-256(careplan_json)

   b. Look up InboundRequest by request_guid:
      - If not found → INSERT (status='new')
      - If found and checksum unchanged → skip (already synced)
      - If found and checksum changed → UPDATE careplan_json, last_synced_at

   c. Upsert ProviderTask:
      - receipt_token = from upstream response
      - provider_guid = PROVIDER_GUID
      - patient_name, careplan_title, etc. = extracted from careplan_json
      - status = 'dispatched' (if new) or preserve current status (if updated)

   d. Upsert CarePlanCache:
      - receipt_token = same
      - careplan_json = full careplan from upstream

   e. Insert TaskAuditLog entry:
      - action = 'sync'
      - payload_snapshot = { request_guid, checksum, is_new: bool }

5. Update sync_state:
   - last_sync_at = now
   - requests_synced += new_count
   - last_error = null

6. On error:
   - Log error
   - Update sync_state.last_error
   - Do NOT clear previous data (local cache is not source of truth, but
     must not lose what it has)
   - Retry on next interval
```

### Sync scheduling

Two options (both implemented, operator chooses):

**Option A — Background thread** (default for development):
- A daemon thread inside the Flask app runs the sync loop
- Controlled by `SYNC_INTERVAL_SECONDS` and `SYNC_ENABLED`
- Simple, no extra infrastructure

**Option B — External cron/systemd timer** (recommended for production):
- A CLI command: `flask sync run`
- Called by cron or systemd timer
- Better observability, no thread management
- Example cron: `* * * * * cd /path/to/provider_portal && venv/bin/flask sync run >> logs/sync.log 2>&1`

Both options use the same `RequestSubscriptionService` — only the trigger differs.

---

## 6) Assumed Upstream API Contract

Since the exact `request.pdhc.se` API is not yet confirmed, this is the assumed response format. The sync client will be built with a mapping layer so adjustments are isolated.

### Assumed: GET {REQUEST_SERVICE_URL}/requests

**Request:**
```
GET /api/v1/requests?provider_guid={guid}&since={iso-datetime}
X-API-Key: {sso-key}
```

**Assumed response:**
```json
{
  "requests": [
    {
      "request_guid": "uuid",
      "receipt_token": "string",
      "provider_guid": "uuid",
      "provider_name": "string",
      "status": "active",
      "created_at": "ISO-8601",
      "updated_at": "ISO-8601",
      "careplan": {
        "careplan_guid": "uuid",
        "title": "string",
        "patient": {
          "patient_guid": "uuid",
          "name": "string"
        },
        "activities": [
          {
            "activity_guid": "uuid",
            "title": "string",
            "transactions": [
              {
                "transaction_guid": "uuid",
                "concept_guid": "uuid",
                "concept_name": "string",
                "response_type": "numeric|categorical|text",
                "valueset_values": [],
                "unit": "string|null",
                "required": true
              }
            ]
          }
        ],
        "dispatch_metadata": {
          "dispatched_at": "ISO-8601",
          "due_at": "ISO-8601|null",
          "priority": "routine|urgent"
        }
      }
    }
  ],
  "cursor": "string|null",
  "has_more": false
}
```

### Mapping layer

A `RequestMapper` class translates the upstream response into local models. If the actual API differs, only this mapper needs to change:

```python
class RequestMapper:
    @staticmethod
    def to_inbound_request(upstream_data) -> dict:
        # Maps upstream JSON to InboundRequest fields

    @staticmethod
    def to_provider_task(upstream_data) -> dict:
        # Maps upstream JSON to ProviderTask fields

    @staticmethod
    def to_careplan_cache(upstream_data) -> dict:
        # Maps upstream careplan to CarePlanCache fields
```

---

## 7) Authentication Flow with SSO

```
1. Instance starts with SSO_API_KEY in .env
   (key issued by operator via sso.pdhc.se for this provider)

2. On each sync request to request.pdhc.se:
   - Send X-API-Key: {SSO_API_KEY}
   - request.pdhc.se validates against sso.pdhc.se

3. If key is rejected (401/403):
   - Log error with clear message
   - Set sync_state.last_error
   - Do not retry until next interval (avoid flooding)

4. Future: if sso.pdhc.se moves to OAuth/Bearer tokens:
   - Add token exchange step before sync
   - SSO_API_KEY becomes client_secret
   - Sync sends Bearer token instead
   - Change isolated to auth layer only
```

---

## 8) Impact on Existing Code

### Config changes
- Add new env vars to `config.py`: `PROVIDER_GUID`, `PROVIDER_NAME`, `REQUEST_SERVICE_URL`, `SSO_API_KEY`, `SYNC_INTERVAL_SECONDS`, `SYNC_ENABLED`

### New files
| File | Purpose |
|------|---------|
| `app/models/inbound_request.py` | InboundRequest model |
| `app/models/sync_state.py` | SyncState model |
| `app/services/subscription.py` | RequestSubscriptionService |
| `app/services/request_mapper.py` | Upstream-to-local data mapper |
| `app/services/sync_scheduler.py` | Background thread / CLI trigger |
| `app/cli.py` | Flask CLI commands (`flask sync run`, `flask sync status`) |
| `tests/test_subscription.py` | Subscription service tests |
| `tests/test_mapper.py` | Mapper tests |

### Modified files
| File | Change |
|------|--------|
| `app/models/__init__.py` | Add InboundRequest, SyncState imports |
| `app/__init__.py` | Register CLI commands, optionally start sync thread |
| `config.py` | Add subscription config vars |
| `.env` | Add instance identity and upstream vars |
| `templates/dashboard.html` | Show sync status (last sync, error, count) |

### No changes to
- Existing API endpoints (they continue to work on ProviderTask)
- Existing services (acknowledge, report, receipt — unchanged)
- Existing tests (all 59 remain valid)

---

## 9) Dashboard Sync Status

The web dashboard will show sync status:

```
┌─────────────────────────────────┐
│ Sync Status                     │
│ Provider: Lab Karolinska        │
│ GUID: abc-123-...               │
│ Last sync: 2026-03-20 14:30 UTC │
│ Requests synced: 47             │
│ Status: ● OK                    │
│ [Sync Now]                      │
└─────────────────────────────────┘
```

If sync has errors:
```
│ Status: ● Error                 │
│ Last error: 401 Unauthorized    │
│ Check SSO key configuration     │
```

---

## 10) CLI Commands

```bash
# Manual sync (one-shot)
flask sync run

# Check sync status
flask sync status

# Reset sync cursor (re-sync all)
flask sync reset
```

---

## 11) Security Considerations

1. **SSO key storage**: stored in `.env`, never committed to git. Same bcrypt-at-rest rules as local API keys do not apply here — this is an outbound credential, stored as plaintext in `.env` (standard for service-to-service keys).

2. **Provider isolation**: each instance only requests data for its own `PROVIDER_GUID`. The upstream service enforces this server-side. The local portal double-checks `provider_guid` on every inbound record.

3. **Data integrity**: checksums prevent processing stale/duplicate data. Raw `careplan_json` is preserved in `inbound_requests` for audit. The working copy in `ProviderTask` can diverge (acknowledge/complete) without affecting the raw record.

4. **Network failure**: sync failures are logged but do not corrupt local state. The portal continues to operate on cached data. Queue reconciliation resumes on next successful sync.

---

## 12) Testing Strategy

| Test | What it verifies |
|------|------------------|
| test_sync_new_requests | New requests create InboundRequest + ProviderTask + CarePlanCache |
| test_sync_unchanged_skipped | Same checksum → no update |
| test_sync_updated_request | Changed checksum → careplan_json updated, ProviderTask status preserved |
| test_sync_auth_failure | 401 from upstream → error logged, no data lost |
| test_sync_network_error | Connection error → error logged, retry on next interval |
| test_sync_duplicate_guid | Same request_guid twice → upsert, not duplicate |
| test_mapper_upstream_format | Mapper correctly extracts fields from upstream JSON |
| test_mapper_missing_fields | Mapper handles missing optional fields gracefully |
| test_sync_state_tracking | Cursor/timestamp updated after successful sync |
| test_sync_audit_trail | Each sync creates audit log entries |
| test_provider_guid_mismatch | Request with wrong provider_guid → rejected |
| test_cli_sync_run | `flask sync run` executes one sync cycle |
| test_cli_sync_status | `flask sync status` shows current state |

---

## 13) Open Questions for Review

1. **Upstream API contract**: is the assumed response format in Section 6 close? What is the actual endpoint path and response structure?

2. **Auth mechanism**: does `request.pdhc.se` accept `X-API-Key` directly, or does it require a token exchange via `sso.pdhc.se` first?

3. **Sync direction**: is this purely pull (portal fetches), or should we also prepare a webhook receiver for push notifications from `request.pdhc.se`?

4. **Cursor/pagination**: does the upstream API support `since` timestamp filtering? Cursor-based pagination? Or do we always fetch all active requests?

5. **Request lifecycle**: when a request is completed (report submitted) on the portal side, should this status be pushed back to `request.pdhc.se`? If so, via what endpoint?

6. **Port allocation for multiple instances**: should colocated instances use 9070/9074/9078 (skipping by 4), or a different scheme?

---

## 14) Implementation Sequence

If approved:

1. Add new models (`InboundRequest`, `SyncState`) and migration
2. Build `RequestMapper` with assumed upstream format
3. Build `RequestSubscriptionService` with sync logic
4. Add CLI commands (`flask sync run/status/reset`)
5. Add background sync thread option
6. Update dashboard with sync status
7. Write all tests from Section 12
8. Update `.env`, `config.py`, `requirements.txt` (add `requests` library)
9. Update `progress.md`, `changed_files.md`
