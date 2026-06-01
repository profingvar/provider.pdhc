# Provider Portal — Auth Scope Matrix

## Scope Definitions

| Scope   | Description                                           |
|---------|-------------------------------------------------------|
| `read`  | Read provider tasks, careplan details, receipts, audit|
| `write` | Acknowledge tasks, submit reports, manage API keys    |

## Endpoint-to-Scope Mapping

| Method | Endpoint                                        | Required Scope | Notes                          |
|--------|-------------------------------------------------|----------------|--------------------------------|
| GET    | /api/v1/provider-tasks/{receipt_token}           | `read`         |                                |
| GET    | /api/v1/provider-tasks/my                        | `read`         |                                |
| POST   | /api/v1/provider-tasks/{receipt_token}/accept     | `write`        | Idempotent                     |
| POST   | /api/v1/provider-tasks/{receipt_token}/report     | `write`        | Idempotent (same payload hash) |
| GET    | /api/v1/provider-tasks/{receipt_token}/careplan-details | `read`  |                                |
| GET    | /api/v1/provider-receipts                        | `read`         |                                |
| GET    | /api/v1/audit-log                                | `read`         |                                |
| GET    | /api/v1/audit-log/{guid}                         | `read`         |                                |
| POST   | /api/v1/api-keys                                 | `write`        | Key shown once at creation     |
| POST   | /api/v1/api-keys/{guid}/revoke                   | `write`        |                                |
| POST   | /api/v1/api-keys/{guid}/rotate                   | `write`        | Revokes old, issues new        |
| POST   | /api/v1/inbound/push                             | `X-Push-Secret`| Mutual auth, no API key        |
| POST   | /api/v1/receipts/ingest                          | `X-Service-Key`| Internal gateway service key   |

## Authorization Rules

1. **Most endpoints require `X-API-Key` header** — missing key returns 401.
2. **Invalid/expired/revoked key** returns 401.
3. **Valid key, wrong scope** returns 403 with code `AUTH_SCOPE_MISMATCH`.
4. **Provider isolation** — a provider can only access their own tasks, receipts, audit entries, and keys. Cross-provider access is blocked at the service layer.
5. **Bootstrap key** — created from `.env` `BOOTSTRAP_API_KEY` on first run, with `read,write` scopes. Must be rotated in production.
6. **Push reception** (`POST /inbound/push`) uses `X-Push-Secret` header for mutual auth with request.pdhc. No API key required.
7. **Gateway receipt ingestion** (`POST /receipts/ingest`) uses `X-Service-Key` header for internal service auth with gateway.pdhc. No API key required.

## Key Lifecycle

```
 Create (POST /api-keys)
    │
    ▼
  Active ──── Rotate (POST /api-keys/{guid}/rotate)
    │              │
    │              ├─→ Old key: Revoked
    │              └─→ New key: Active
    │
    ▼
  Revoke (POST /api-keys/{guid}/revoke)
    │
    ▼
  Revoked (permanent, cannot be undone)
```

## Key Storage Rules

- Keys are bcrypt-hashed at rest — plaintext is never stored
- Raw key is returned exactly once at creation/rotation
- Expiry is optional; enforced on every request if set
- Revocation is immediate and audit-logged

## Future: SSO Integration

SSO via `sso.pdhc.se` will be layered on top of API key auth. The scope model is designed to be compatible — SSO tokens will map to the same `read`/`write` scopes. API key auth will remain available for machine-to-machine integrations.
