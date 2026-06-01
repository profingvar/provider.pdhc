# Provider Portal — API Contract Documentation

Base URL: `http://localhost:9070/api/v1`

All endpoints require `X-API-Key` header unless noted.

---

## Authentication

All protected endpoints require a valid API key in the `X-API-Key` header.

```
X-API-Key: <your-api-key>
```

Keys are bcrypt-hashed at rest. Each key has assigned scopes (`read`, `write`), optional expiry, and can be revoked.

---

## Provider Tasks

### GET /provider-tasks/{receipt_token}

Fetch a single provider task by receipt token.

**Scope**: `read`

**Response 200**:
```json
{
  "guid": "uuid",
  "receipt_token": "string",
  "provider_guid": "uuid",
  "status": "dispatched|acknowledged|in_progress|completed|cancelled",
  "is_active": false,
  "patient_guid": "uuid|null",
  "patient_name": "string|null",
  "careplan_guid": "uuid|null",
  "careplan_title": "string|null",
  "dispatched_at": "ISO-8601|null",
  "due_at": "ISO-8601|null",
  "acknowledged_at": "ISO-8601|null",
  "completed_at": "ISO-8601|null",
  "notes": "string|null",
  "created_at": "ISO-8601"
}
```

**Errors**: 401, 403, 404

---

### GET /provider-tasks/my

List tasks for the authenticated provider.

**Scope**: `read`

**Query parameters**:
| Param    | Type   | Default | Description                |
|----------|--------|---------|----------------------------|
| `status` | string | —       | Filter by status           |
| `limit`  | int    | 50      | Max results                |

**Response 200**: Array of task objects.

**Errors**: 401, 403

---

### POST /provider-tasks/{receipt_token}/accept

Acknowledge/accept a task. Idempotent — re-acknowledging an already acknowledged task returns 200.

**Scope**: `write`

**Request body** (optional):
```json
{
  "notes": "string"
}
```

**Response 200**: Updated task object with `status: "acknowledged"`.

**Errors**: 401, 403, 404, 409 (task not in acknowledgeable state)

**Idempotency**: Calling accept on an already-acknowledged task returns 200 with current state.

---

### POST /provider-tasks/{receipt_token}/report

Submit completion report. Supports manual and guided (observation-based) payloads. Idempotent — re-submitting the same payload returns the existing receipt.

**Scope**: `write`

**Request body**:
```json
{
  "provider_payload": {
    "observations": [
      {
        "transaction_guid": "uuid",
        "value": "string|number",
        "recorded_at": "ISO-8601",
        "notes": "string (omit if empty)"
      }
    ]
  },
  "notes": "string|null",
  "receipt_message": "string|null"
}
```

> **Minimal payload**: `concept_guid` and `unit` are **not** sent by the provider. The gateway derives these from the ServiceRequest context (transaction map). Only `transaction_guid`, `value`, and `recorded_at` are required per observation; `notes` is optional and should be omitted entirely (not sent as null) when not present.
```

For manual mode, `provider_payload` can be any JSON object (without `observations` key).

**Response 200**:
```json
{
  "task": { "...task object with status: completed..." },
  "receipt": {
    "guid": "uuid",
    "receipt_token": "string",
    "provider_guid": "uuid",
    "status": "submitted",
    "message": "string",
    "submitted_at": "ISO-8601"
  }
}
```

**Errors**: 400 (missing payload), 401, 403, 404, 409 (already completed), 422 (guided validation failure — details include missing/invalid transactions)

**Idempotency**: Submitting the same `provider_payload` hash returns 200 with existing receipt.

---

### GET /provider-tasks/{receipt_token}/careplan-details

Fetch careplan details linked to a task for guided response.

**Scope**: `read`

**Response 200**:
```json
{
  "patient": { "name": "string" },
  "careplan": { "title": "string" },
  "activities": [
    {
      "transactions": [
        {
          "transaction_guid": "uuid",
          "concept_guid": "uuid",
          "concept_name": "string",
          "response_type": "numeric|categorical|text",
          "valueset_values": ["string"] ,
          "unit": "string|null",
          "required": true
        }
      ]
    }
  ]
}
```

**Errors**: 401, 403, 404 (task or careplan not found/cached)

---

## Receipts

### GET /provider-receipts

List submission receipts for the authenticated provider.

**Scope**: `read`

**Query parameters**:
| Param           | Type   | Default | Description                     |
|-----------------|--------|---------|---------------------------------|
| `receipt_token` | string | —       | Filter by task receipt token    |
| `limit`         | int    | 50      | Max results                     |

**Response 200**: Array of receipt objects.

---

## Audit Log

### GET /audit-log

List audit entries for the authenticated provider.

**Scope**: `read`

**Query parameters**:
| Param           | Type   | Default | Description                     |
|-----------------|--------|---------|---------------------------------|
| `receipt_token` | string | —       | Filter by task receipt token    |
| `limit`         | int    | 50      | Max results                     |

**Response 200**:
```json
[
  {
    "guid": "uuid",
    "receipt_token": "string",
    "provider_guid": "uuid",
    "action": "acknowledge|report|sync",
    "payload_snapshot": {},
    "created_at": "ISO-8601"
  }
]
```

### GET /audit-log/{guid}

Fetch a single audit entry.

**Scope**: `read`

**Errors**: 404

---

## API Key Management

### POST /api-keys

Create a new API key for the authenticated provider.

**Scope**: `write`

**Request body**:
```json
{
  "scopes": "read|read,write",
  "label": "string|null",
  "expires_in_days": 30
}
```

**Response 201**:
```json
{
  "guid": "uuid",
  "key": "raw-key-shown-once",
  "scopes": "string",
  "label": "string|null",
  "expires_at": "ISO-8601|null",
  "message": "Store this key securely. It will not be shown again."
}
```

### POST /api-keys/{guid}/revoke

Revoke an API key immediately.

**Scope**: `write`

**Response 200**: `{ "message": "Key revoked", "guid": "uuid" }`

### POST /api-keys/{guid}/rotate

Revoke old key and issue a new one with the same scopes.

**Scope**: `write`

**Response 201**:
```json
{
  "old_key_guid": "uuid",
  "new_key_guid": "uuid",
  "key": "new-raw-key-shown-once",
  "scopes": "string",
  "message": "Old key revoked. Store new key securely."
}
```

---

## Inbound Push Reception

### POST /inbound/push

Receive a pushed FHIR Bundle from request.pdhc. Not authenticated via API key — uses mutual auth via shared push secret.

**Headers**:
```
X-Push-Secret: <shared-secret>
Content-Type: application/fhir+json
```

**Request body**: FHIR Bundle with `meta.tag` entries containing delivery metadata:
- `receipt_token` — delivery receipt identifier (required)
- `grant_token` — HMAC composite key for report submission
- `contract_guid` — governing contract
- `organisation_guid` — provider organisation
- `expires_at` — grant expiry timestamp (ISO-8601)

**Response 202**:
```json
{
  "status": "accepted",
  "receipt_token": "string",
  "request_guid": "uuid"
}
```

**Errors**: 400 (invalid bundle/missing receipt_token), 401 (invalid push secret), 503 (not configured)

---

## Gateway Receipt Ingestion

### POST /receipts/ingest

Receive observation receipt pushed from gateway.pdhc after it accepts a provider report. Authenticated via internal service key.

**Headers**:
```
X-Service-Key: <gateway-service-key>
```

**Request body**:
```json
{
  "receipt_guid": "uuid (required)",
  "service_request_guid": "uuid (required)",
  "patient_guid": "uuid",
  "provider_org_guid": "uuid",
  "contract_guid": "uuid",
  "observations_stored": 3,
  "accepted_at": "ISO-8601",
  "payload_hash": "sha256-hex"
}
```

**Response 202**:
```json
{
  "status": "accepted",
  "receipt_guid": "uuid",
  "action": "created|duplicate"
}
```

**Errors**: 400 (missing required fields), 401 (invalid service key), 503 (not configured)

**Idempotency**: Duplicate `receipt_guid` returns `action: "duplicate"` without error.

---

## Error Response Format

All API errors return:

```json
{
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": []
}
```

### HTTP Status Codes

| Code | Meaning                          | Error Code Examples           |
|------|----------------------------------|-------------------------------|
| 400  | Invalid token/payload/validation | VALIDATION_ERROR              |
| 401  | Missing or invalid API key       | AUTH_MISSING, AUTH_INVALID     |
| 403  | Valid key, wrong scope/provider  | AUTH_SCOPE_MISMATCH           |
| 404  | Task/careplan/resource not found | TASK_NOT_FOUND, NOT_FOUND     |
| 405  | Method not allowed               | METHOD_NOT_ALLOWED            |
| 409  | Duplicate/conflicting action     | CONFLICT                      |
| 422  | Semantic validation failure      | VALIDATION_ERROR (with details)|
| 500  | Internal processing failure      | INTERNAL_ERROR                |

### Guided Submission Validation Details (422)

When guided observations fail validation, `details` contains:
```json
[
  {
    "transaction_guid": "uuid",
    "concept_name": "Blood Pressure",
    "message": "Required observation missing"
  }
]
```
