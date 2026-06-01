# Data Package Reference — Provider.pdhc

**Date:** 2026-04-02 (revised)
**Scope:** What the provider receives in a ServiceRequest, what the provider sends back to the gateway, and how the gateway reconstructs context from the stored ServiceRequest

---

## 1) Inbound: What the Provider Receives

When a FHIR ServiceRequest containing a CarePlan (e.g. "Astma Monitoring") is delivered to provider.pdhc — via push or poll — the following data arrives:

### Bundle Delivery Metadata (meta.tag)

- `receipt_token` — bearer token for acknowledging delivery
- `grant_token` — HMAC composite key for sending data back
- `expires_at` — grant expiry timestamp
- `organisation_guid` — receiving provider org identity
- `contract_guid` — governing contract
- `service_request_guid` — traceability reference
- `patient_guid` — the data subject

### ServiceRequest Envelope

- `id` — ServiceRequest GUID
- `status` — lifecycle state (active)
- `intent` — order
- `priority` — routine/urgent
- `code.text` — "Astma Monitoring" (PlanDefinition title)
- `authoredOn` — when the request was created
- `instantiatesCanonical` — reference to PlanDefinition (full URL: `https://plan.pdhc.se/api/v1/plandefinitions/<guid>`)
- `basedOn` — full reference to Contract including resolvable URL: `https://contract.pdhc.se/fhir/Contract/<contract_guid>`
- `occurrencePeriod.start` — validity start
- `occurrencePeriod.end` — validity end
- `note` — clinician's free text notes

### ServiceRequest.subject (Patient)

- `reference` — Patient/<guid>
- `display` — patient name

### ServiceRequest.requester (Clinician)

- `reference` — Practitioner/<guid>
- `display` — clinician name
- `extension.valueReference` — requester Organisation (guid + name)

### Contained Patient Excerpt

- `name` — given + family
- `gender`
- `birthDate`
- `identifier` — patient identifiers

### Contained Goal

- `lifecycleStatus` — planned
- `description.text` — e.g. "Uppna astmakontroll"
- `description.coding` — concept GUID + display
- `priority` — high/medium/low
- `target.detailQuantity` — target value + comparator

### Contained CarePlan

- `title` — "Astma Monitoring"
- `description` — plan description
- `status` — active
- `instantiatesCanonical` — PlanDefinition reference
- `goal` — references to contained Goal resources

### CarePlan.activity (the "Astma Monitoring" Activity)

- `detail.code.text` — activity title
- `detail.code.coding[]` — concept GUIDs + display names for each transaction
- `detail.description` — activity description
- `detail.status` — not-started
- `detail.performer` — who performs (e.g. "Sjukskoterska")
- `detail.scheduledTiming.repeat.frequency` — how often (e.g. 2)
- `detail.scheduledTiming.repeat.period` — period value (e.g. 1)
- `detail.scheduledTiming.repeat.periodUnit` — period unit (d/wk/mo)
- `detail.scheduledTiming.repeat.duration` — session duration
- `detail.scheduledTiming.repeat.durationUnit` — duration unit (min)
- `detail.quantity` — expected value from first transaction
- `detail.extension[expected-range].low` — range minimum
- `detail.extension[expected-range].high` — range maximum

### CarePlan.activity._pdhc_transactions[] (Per Transaction)

- `concept_guid` — the medical concept identifier
- `concept_name` — e.g. "Spirometri", "Astma Control Questionnaire"
- `requirement_type` — required or recommended
- `expected_value` — expected numeric value (if applicable)
- `unit` — measurement unit GUID
- `range_min` — acceptable minimum
- `range_max` — acceptable maximum

### Contained Questionnaire (If Forms Attached)

- `id` — form GUID
- `title` — form display name
- `item[]` — form questions with response_type, valueset, unit, range extensions

### Binary Entries (If Render-Ready Forms Attached)

- `contentType` — application/json
- `data` — base64-encoded pre-rendered form snapshot
- `meta.tag` — form_guid + render_ready title

---

## 2) Outbound: What the Provider Sends Back to the Gateway

The provider sends a **minimal return payload**. The gateway reconstructs full context by looking up the stored ServiceRequest and resolving the contract from contract.pdhc. The provider does not need to echo back fields that the gateway already has.

### What the Provider Sends

```
POST /api/v1/provider/report/{service_request_guid}
Header: X-Provider-Token: <PAT>
```

```json
{
  "patient_guid": "<required — audit + defense in depth>",
  "grant_token": "<required — authorization proof>",
  "status": "completed",
  "report_payload": {
    "observations": [
      {
        "transaction_guid": "<which transaction this answers>",
        "value": "<the measured/observed value>",
        "notes": "<optional provider notes>",
        "recorded_at": "<ISO-8601 timestamp>"
      }
    ]
  }
}
```

### Field-by-Field Explanation

**Sent by provider — required:**

- `service_request_guid` (URL path) — identifies the ServiceRequest
- `patient_guid` (body) — the data subject; included for GDPR audit trail and as a defense-in-depth cross-check against the SR's subject
- `grant_token` (body) — proves the provider was authorized for this SR; the only field the gateway cannot derive on its own
- `status` (body) — provider's completion status: `completed`, `accepted`, or `rejected`

**Sent by provider — per observation:**

- `transaction_guid` — which transaction in the CarePlan this value answers
- `value` — the measured/observed data (provider-entered)
- `notes` — optional free text (provider-entered)
- `recorded_at` — when the observation was taken (provider-entered)

**NOT sent by provider — gateway derives these:**

- `organisation_guid` — derived from the validated PAT
- `contract_guid` — looked up from the ServiceRequest's `basedOn` reference and the grant record
- `concept_guid` — looked up from the transaction definition in the SR's contained CarePlan
- `unit` — looked up from the transaction definition in the SR's contained CarePlan
- `expected_value`, `range_min`, `range_max` — looked up from the transaction definition
- `requirement_type` — looked up from the transaction definition
- Requester, PlanDefinition, Goals — all in the stored SR

---

## 3) Gateway Reconstruction: How the Gateway Rebuilds Full Context

When gateway.pdhc receives the minimal return payload, it reconstructs the complete picture:

```
STEP 1: Authenticate
  X-Provider-Token → validate PAT
  → derive: organisation_guid, contract_guid (from PAT record)

STEP 2: Load ServiceRequest
  service_request_guid → fetch SR from request.pdhc (or local cache)
  → derive: patient_guid (SR.subject), requester, PlanDefinition ref,
            contained CarePlan, Goals, occurrencePeriod

STEP 3: Cross-check patient
  submitted patient_guid == SR.subject.reference
  → reject with audit if mismatch (defense in depth)

STEP 4: Validate grant
  Look up DataExchangeGrant by sr_guid + org_guid (from PAT)
  hmac.compare_digest(stored_grant_token, submitted_grant_token)
  Check: not expired, not revoked, not over max_uses
  → reject 403 if invalid

STEP 5: Resolve contract scope (LOOKUP, not copy)
  contract_guid (from SR.basedOn or grant record)
  → query contract.pdhc: GET /fhir/Contract/{contract_guid}
  → extract permitted_concepts[] from contract scope
  → cache in guid_resolution_cache with TTL

STEP 6: Validate transactions against contract scope
  For each observation.transaction_guid:
    → look up transaction in SR's contained CarePlan
    → extract concept_guid from the transaction definition
    → check concept_guid is in contract.permitted_concepts[]
    → reject 403 if concept not in scope

STEP 7: Enrich each observation
  For each observation.transaction_guid:
    → from the SR's CarePlan, reconstruct:
      concept_guid, concept_name, unit, expected_value,
      range_min, range_max, requirement_type
    → from the SR's Goals, link clinical target context
    → from the PlanDefinition, link clinical template semantics

STEP 8: Store + vectorize
  Store observation with full resolved context
  Generate embedding vector for CDR
  Audit log with data_subject_guid = patient_guid
```

---

## 4) Contract Scope: Lookup, Not Copy

**Design decision:** The contract is looked up from contract.pdhc at validation time, not stored as a copy in the ServiceRequest or grant.

### Why Lookup Is Better

| Concern | Copy | Lookup |
|---------|------|--------|
| **Contract amended** | Provider submits against stale snapshot | Gateway sees current contract |
| **Contract revoked** | Stale copy still says "allowed" | Lookup returns revoked status |
| **Scope narrowed** | Provider submits for concepts no longer permitted | Gateway rejects at step 6 |
| **Single source of truth** | contract.pdhc + N copies in SRs | contract.pdhc only |
| **Storage** | Duplicated in every SR | Referenced by GUID |
| **Performance** | No network call | Cached in `guid_resolution_cache` with TTL |

### What the Contract Should Contain for Transaction-Level Access Control

The contract scope is split into **two distinct concept lists**:

1. **Outbound concepts** (`request_scope`) — concepts that the requester is permitted to include in ServiceRequests sent to this provider. These define what the provider is asked to do.
2. **Return concepts** (`return_scope`) — concepts that the provider is permitted to submit observations for in their report back. These may be a subset, superset, or entirely different set from the outbound concepts. Each return concept is marked as `obligatory` or `optional`.

This two-list design reflects reality: a contract might authorize sending a broad care plan to a provider, but only permit (or require) the provider to report back on specific measurements.

All concept references use resolvable URLs pointing to the vocabulary service at plan.pdhc.

```json
{
  "resourceType": "Contract",
  "id": "<contract_guid>",
  "status": "executed",
  "signer": [
    { "party": { "reference": "Organization/<requester_org_guid>" } },
    { "party": { "reference": "Organization/<provider_org_guid>" } }
  ],
  "term": [
    {
      "type": { "text": "request_scope" },
      "offer": {
        "text": "Concepts permitted in ServiceRequests to this provider"
      },
      "asset": [
        {
          "type": [{ "text": "outbound_concept" }],
          "typeReference": [
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_spirometri>",
              "display": "Spirometri"
            },
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_acq>",
              "display": "Astma Control Questionnaire"
            },
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_peakflow>",
              "display": "Peak Expiratory Flow"
            }
          ]
        }
      ]
    },
    {
      "type": { "text": "return_scope" },
      "offer": {
        "text": "Concepts the provider may (or must) submit observations for"
      },
      "asset": [
        {
          "type": [{ "text": "obligatory_return" }],
          "typeReference": [
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_spirometri>",
              "display": "Spirometri"
            }
          ]
        },
        {
          "type": [{ "text": "optional_return" }],
          "typeReference": [
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_acq>",
              "display": "Astma Control Questionnaire"
            },
            {
              "reference": "https://plan.pdhc.se/api/v1/concepts/<concept_guid_peakflow>",
              "display": "Peak Expiratory Flow"
            }
          ]
        }
      ]
    }
  ]
}
```

**What the gateway extracts at report ingestion:**

From `return_scope` term:
- `obligatory_return` asset → concept GUIDs the provider **must** include in a completed report
- `optional_return` asset → concept GUIDs the provider **may** include
- Any concept not in either list → rejected (403)

From `request_scope` term (used at ServiceRequest finalization, not at report ingestion):
- `outbound_concept` asset → concept GUIDs allowed in the CarePlan sent to this provider
- request.pdhc validates CarePlan transactions against this list before push

**Gateway validation logic:**
1. Each submitted `transaction_guid` is resolved to its `concept_guid` via the SR's CarePlan
2. The `concept_guid` must appear in either `obligatory_return` or `optional_return`
3. If report `status` is `completed`: all `obligatory_return` concepts must be present in the submission
4. If report `status` is `accepted` or `rejected`: obligatory check is skipped (provider may accept/reject without submitting observations)

**Edge cases:**
- If the contract has no `return_scope` term → all concepts in the SR's CarePlan are permitted as optional returns (backward compatibility)
- If the contract has no `request_scope` term → no outbound concept restriction (backward compatibility)
- If the contract is revoked → all submissions rejected
- If a concept is removed from the return scope → future submissions for that concept rejected, existing data unaffected

### Vocabulary Service Reference

All concept references in the contract resolve to the vocabulary/concept API hosted by **plan.pdhc**:

| Endpoint | URL | Description |
|----------|-----|-------------|
| Concept by GUID | `https://plan.pdhc.se/api/v1/concepts/<guid>` | Full concept definition (name, response_type, unit, range, valueset) |
| Concept list | `https://plan.pdhc.se/api/v1/concepts` | Search/filter concepts (`?search=`, `?concept_type=`, `?response_type=`) |
| Concept values | `https://plan.pdhc.se/api/v1/concepts/<guid>/values` | Valueset values for a concept (categorical options) |
| Response types | `https://plan.pdhc.se/api/v1/response-types` | All response types (numeric, categorical, text, boolean, date, etc.) |
| Units | `https://plan.pdhc.se/api/v1/units` | All measurement units |
| ValueSets | `https://plan.pdhc.se/api/v1/valuesets` | All value set definitions |
| ValueSet values | `https://plan.pdhc.se/api/v1/valuesets/<guid>/values` | Values in a specific valueset |
| Canonical libraries | `https://plan.pdhc.se/api/v1/canonical-libs` | Terminology authorities (SNOMED-CT, LOINC, ICD-10, etc.) |
| Capability statement | `https://plan.pdhc.se/api/v1/capability-statement` | Full API capability listing |

All GET endpoints on the vocabulary API are **public** (no authentication required). Write endpoints require SSO authentication with `read_write` role.

Local development base URL: `http://localhost:9030/api/v1`

### What Is Stored vs Referenced

```
ServiceRequest (in request.pdhc):
  basedOn: Contract/<contract_guid>     ← reference only, not a copy
  contained: [CarePlan, Patient, Goals] ← these ARE copies (snapshots at finalization)

DataExchangeGrant (in request.pdhc):
  contract_guid                         ← reference, for lookup key

Contract (in contract.pdhc):
  Full FHIR Contract resource           ← the authoritative source
  Signer orgs, terms, scope, status     ← always current
```

The CarePlan is a snapshot (it was edited by the clinician before finalization — the snapshot captures their intent). The Contract is live (it governs ongoing authorization and can be amended or revoked).

---

## 5) Summary: Minimal Return Payload

```
PROVIDER SENDS                    GATEWAY DERIVES
═══════════════                   ═══════════════

service_request_guid (URL)   →   Loads full SR from request.pdhc
                                  → patient_guid (cross-check)
                                  → CarePlan (transactions, concepts, units, ranges)
                                  → Goals, PlanDefinition reference
                                  → Requester identity

X-Provider-Token (header)    →   Validates PAT
                                  → organisation_guid
                                  → contract_guid (from PAT record)

grant_token                  →   Proves authorization
                                  (cannot be derived — only provider has it)

patient_guid                 →   Audit trail (GDPR data_subject_guid)
                                  + cross-check against SR.subject

status                       →   Provider's completion assessment

Per observation:
  transaction_guid           →   Resolves concept_guid, unit, expected_value,
                                  range_min, range_max, requirement_type
                                  from SR's contained CarePlan
                                  → Checks concept against contract scope

  value                      →   The actual data (provider-generated)
  notes                      →   Provider commentary (provider-generated)
  recorded_at                →   Observation timestamp (provider-generated)
```

**5 fields from provider. Everything else reconstructed.**

---

## 6) Report Payload — Manual Mode

For non-guided submissions:

```json
{
  "patient_guid": "<required>",
  "grant_token": "<required>",
  "status": "completed",
  "report_payload": { "<freeform JSON>" }
}
```

Manual mode bypasses transaction-level validation (no transaction_guid to check against contract scope). The gateway stores the payload as-is. Contract scope validation applies only to guided observations.

---

## 7) Report Payload — With Visual Content (Future, Analytics Phase)

```json
{
  "patient_guid": "<required>",
  "grant_token": "<required>",
  "status": "completed",
  "report_payload": {
    "observations": [ ... ],
    "diagnostic_report": {
      "resourceType": "DiagnosticReport",
      "presentedForm": [ "<base64 SVGs, chart descriptors>" ],
      "conclusion": "<provider's clinical summary>",
      "contained": [ "<FHIR Observation resources>" ]
    }
  }
}
```

See `docs/widget_content_design.md` for the full visual content design.

---

## 8) Required Reforms: contract.pdhc

contract.pdhc currently stores FHIR Contract resources as opaque JSON blobs (`fhir_contract` column) with minimal structure enforcement. To support transaction-level scope validation, the following changes are needed.

### 8.1 Contract Model — Add Concept Scope

**Current state:** The `ContractRecord` model has only `guid`, `fhir_contract` (JSON), and timestamps. The FHIR Contract shape allows `party[]`, `subject[]`, `topic[]`, and `period`, but has no structured concept scope.

**Change needed:** Add a `term[]` structure to the FHIR Contract resource that specifies permitted concepts for data submission. This does not require a new database column — it lives inside the existing `fhir_contract` JSON — but it requires:

- **Validation in `ensure_contract_shape()`** — accept and validate the `term[]` array with `data_submission_scope` type entries
- **Extraction helper** — a function that takes a Contract GUID and returns the list of permitted concept GUIDs from `term[].asset[].typeReference[]`

```python
# New function in fhir.py or a new contract_scope_service.py
def get_permitted_concepts(contract_guid):
    """Extract permitted concept GUIDs from contract scope terms.
    Returns list of concept_guid strings, or None if no scope defined
    (None = all concepts permitted, backward compatible).
    """
    record = ContractRecord.query.filter_by(guid=contract_guid).first()
    if not record:
        return None
    contract = record.fhir_contract
    concepts = []
    for term in contract.get('term', []):
        if term.get('type', {}).get('text') != 'data_submission_scope':
            continue
        for asset in term.get('asset', []):
            for ref in asset.get('typeReference', []):
                # Extract concept GUID from reference URL
                # "https://pdhc.se/concepts/<guid>" → "<guid>"
                reference = ref.get('reference', '')
                if '/concepts/' in reference:
                    concepts.append(reference.split('/concepts/')[-1])
    return concepts if concepts else None
```

### 8.2 New API Endpoint — Contract Scope Query

**Current state:** `GET /fhir/Contract/{guid}` returns the full FHIR Contract resource. The gateway would have to fetch the entire contract and parse the scope client-side.

**Change needed:** Add a lightweight scope endpoint that returns only the permitted concepts:

```
GET /fhir/Contract/{guid}/scope
```

**Response 200:**
```json
{
  "contract_guid": "<guid>",
  "status": "executed",
  "permitted_concepts": [
    {
      "concept_guid": "<guid>",
      "display": "Spirometri"
    },
    {
      "concept_guid": "<guid>",
      "display": "Astma Control Questionnaire"
    }
  ],
  "scope_defined": true
}
```

**Response when no scope defined (backward compatible):**
```json
{
  "contract_guid": "<guid>",
  "status": "executed",
  "permitted_concepts": null,
  "scope_defined": false
}
```

**Response when contract revoked/terminated:**
```json
{
  "contract_guid": "<guid>",
  "status": "revoked",
  "permitted_concepts": [],
  "scope_defined": true
}
```

**Why a separate endpoint?** The full Contract resource may be large (party arrays, notes, legal text). The gateway only needs the concept list. A dedicated endpoint is cacheable, fast, and avoids transferring unnecessary data on every observation submission.

### 8.3 Contract Admin UI — Scope Editor

**Current state:** The contract admin UI allows creating/editing FHIR Contract JSON. There is no structured UI for managing concept scope.

**Change needed:** Add a scope editor section in the contract create/edit form:

- Dropdown or search to select concepts from plan.pdhc's concept library
- Display selected concepts as a list with remove buttons
- On save, inject the `term[]` structure into the FHIR Contract JSON before storing
- Show current scope on contract detail view

### 8.4 Contract Status Check for Gateway

**Current state:** `GET /fhir/Contract/{guid}` returns the full resource including status. No lightweight status-only endpoint.

**Change needed:** The scope endpoint (8.2) already returns `status`. The gateway should check contract status before accepting data:

- `executed` → accept submissions within scope
- `revoked`, `terminated`, `cancelled` → reject all submissions (403)
- `offered`, `negotiable` → contract not yet active, reject (403)

### 8.5 Summary of contract.pdhc Changes

| Change | File | Type |
|--------|------|------|
| Validate `term[]` with `data_submission_scope` in FHIR shape | `fhir.py` | Modify |
| `get_permitted_concepts(guid)` helper function | `fhir.py` or new `scope_service.py` | New |
| `GET /fhir/Contract/{guid}/scope` endpoint | `main.py` | New |
| Scope editor in contract admin UI | templates | Modify |
| Tests: scope extraction, scope endpoint, revoked contract | tests | New |

---

## 9) Required Reforms: request.pdhc

request.pdhc holds the ServiceRequest, the PAT records, and the DataExchangeGrant records. The gateway needs to query request.pdhc to reconstruct context from a minimal provider return payload.

### 9.1 New Endpoint — ServiceRequest Context for Gateway

**Current state:** `GET /api/v1/ServiceRequest/{guid}` returns the full SR, but it requires SSO auth or internal auth. There is no lightweight, gateway-specific endpoint.

**Change needed:** Add an internal service endpoint that gateway.pdhc can call to fetch the SR context needed for reconstruction:

```
GET /api/v1/internal/service-request/{guid}/context
Header: X-Service-Key: <shared internal key>
```

**Response 200:**
```json
{
  "service_request_guid": "<guid>",
  "status": "active",
  "patient_guid": "<guid>",
  "contract_guid": "<guid or null>",
  "requester_org_guid": "<guid>",
  "requester_user_guid": "<guid>",
  "requester_user_name": "Dr. Jane Doe",
  "plan_definition_guid": "<guid>",
  "period_start": "ISO-8601",
  "period_end": "ISO-8601",
  "transactions": [
    {
      "transaction_guid": "<guid>",
      "concept_guid": "<guid>",
      "concept_name": "Spirometri",
      "unit": "<unit_guid>",
      "unit_display": "% predicted",
      "expected_value": "80",
      "range_min": 70.0,
      "range_max": 120.0,
      "requirement_type": "required"
    },
    {
      "transaction_guid": "<guid>",
      "concept_guid": "<guid>",
      "concept_name": "Astma Control Questionnaire",
      "unit": null,
      "unit_display": null,
      "expected_value": null,
      "range_min": null,
      "range_max": null,
      "requirement_type": "recommended"
    }
  ],
  "goals": [
    {
      "description": "Uppna astmakontroll",
      "concept_guid": "<guid>",
      "priority": "high",
      "target_value": 70.0,
      "target_comparator": ">="
    }
  ]
}
```

**Why a dedicated context endpoint?**
- The full SR FHIR resource is large (contained Patient, CarePlan, Goals, Questionnaires). The gateway only needs the transaction map + metadata.
- The transaction list is pre-extracted from the CarePlan's `_pdhc_transactions[]`, saving the gateway from parsing FHIR contained resources.
- Auth is via internal service key (`X-Service-Key`), not SSO — gateway.pdhc is a trusted internal service.

### 9.2 Implementation — Context Extraction Service

**New file:** `gateway/app/services/context_service.py`

```python
class ContextService:
    @staticmethod
    def get_sr_context(sr_guid):
        """Extract gateway-relevant context from a stored ServiceRequest."""
        sr = ServiceRequest.query.filter_by(guid=sr_guid).first()
        if not sr:
            return None

        fhir = sr.fhir_resource or {}
        careplan = _extract_contained(fhir, 'CarePlan')
        transactions = _extract_transactions(careplan)
        goals = _extract_goals(fhir)

        return {
            'service_request_guid': sr.guid,
            'status': sr.status,
            'patient_guid': sr.patient_guid,
            'contract_guid': sr.contract_guid,
            'requester_org_guid': sr.requester_org_guid,
            'requester_user_guid': sr.requester_user_guid,
            'requester_user_name': sr.requester_user_name,
            'plan_definition_guid': sr.plan_definition_guid,
            'period_start': sr.period_start.isoformat() if sr.period_start else None,
            'period_end': sr.period_end.isoformat() if sr.period_end else None,
            'transactions': transactions,
            'goals': goals,
        }
```

### 9.3 Internal API Blueprint

**New file:** `gateway/app/api/internal.py`

```
GET  /api/v1/internal/service-request/{guid}/context   — SR context for gateway
POST /api/v1/internal/grant/validate                    — validate grant (alternative to gateway doing it locally)
```

Auth: `X-Service-Key` header, checked against `INTERNAL_SERVICE_KEY` config. Not exposed publicly. Not accessible via PAT or SSO.

### 9.4 Grant Validation — Keep on request.pdhc or Move to Gateway?

**Current state:** The grant is validated on request.pdhc in `report_service.py`. The provider calls request.pdhc's report endpoint, which validates the grant locally.

**New flow:** The provider calls **gateway.pdhc**, which needs to validate the grant. Two options:

**Option A: Gateway calls request.pdhc to validate (recommended)**
```
gateway.pdhc receives report
  → POST /api/v1/internal/grant/validate
    { sr_guid, org_guid, patient_guid, grant_token }
  → request.pdhc validates HMAC, expiry, revocation, max_uses
  → returns { valid: true, contract_guid, grant_type, uses_remaining }
```

**Why A is better:** The HMAC_SECRET stays on request.pdhc. Gateway.pdhc never sees the secret. If the gateway is compromised, the attacker cannot forge grant tokens. The grant validation is a single HTTP call, cacheable for the duration of the request.

**Option B: Share HMAC_SECRET with gateway.pdhc**
The current design shares HMAC_SECRET. This works but means two services hold the critical secret. Option A eliminates this.

### 9.5 Update Report Endpoint — Accept Minimal Payload

**Current state:** `POST /api/v1/provider/report/{sr_guid}` on request.pdhc requires `patient_guid`, `organisation_guid`, `contract_guid`, and `grant_token` in the body.

**Change needed:** If the gateway becomes the primary ingest point (as described in gateway.pdhc's design), the request.pdhc report endpoint should either:

- **Be deprecated** in favor of gateway.pdhc handling reports directly, or
- **Be simplified** to accept the minimal payload (patient_guid + grant_token) and derive the rest internally

If the report endpoint remains on request.pdhc (with gateway as a pass-through or separate ingest point), update validation to:

```python
# Required from provider
patient_guid = body['patient_guid']
grant_token = body['grant_token']

# Derived internally
org_guid = g.provider_org_guid          # from validated PAT
contract_guid = grant.contract_guid     # from grant record lookup
```

Remove the requirement for `organisation_guid` and `contract_guid` in the request body.

### 9.6 Summary of request.pdhc Changes

| Change | File | Type |
|--------|------|------|
| `ContextService.get_sr_context()` | `services/context_service.py` | New |
| `GET /internal/service-request/{guid}/context` | `api/internal.py` | New |
| `POST /internal/grant/validate` | `api/internal.py` | New |
| Internal service key auth middleware | `middleware/auth_middleware.py` | Modify |
| `INTERNAL_SERVICE_KEY` config | `config.py`, `.env` | Modify |
| Simplify report endpoint — derive org/contract from PAT/grant | `api/provider.py`, `services/report_service.py` | Modify |
| Tests: context endpoint, grant validation endpoint, minimal payload | tests | New |

---

## 10) Required Reforms: gateway.pdhc

gateway.pdhc becomes the primary observation ingest point. It receives the minimal payload from providers, reconstructs full context via request.pdhc and contract.pdhc, validates against contract scope, and stores in the CDR.

### 10.1 New Validation Chain

Replace the current "echo-back-everything" validation with the reconstruction flow from Section 3:

```
1. Validate PAT                          (existing — via request.pdhc or local)
2. Load SR context                       (NEW — call request.pdhc internal API)
3. Cross-check patient_guid              (existing logic, new data source)
4. Validate grant                        (call request.pdhc internal API — Option A)
5. Look up contract scope                (NEW — call contract.pdhc scope endpoint)
6. Validate transactions against scope   (NEW)
7. Enrich observations from SR context   (NEW)
8. Store + vectorize                     (existing)
9. Push receipt to provider.pdhc         (existing)
```

### 10.2 Contract Scope Cache

Add contract scope to the existing `guid_resolution_cache`:

```
source_type: 'contract_scope'
source_guid: contract_guid
resolved_json: { permitted_concepts: [...], status: "executed" }
ttl: 300 seconds (5 min — contracts change rarely but revocation must propagate)
```

### 10.3 SR Context Cache

Add SR context to `guid_resolution_cache`:

```
source_type: 'sr_context'
source_guid: service_request_guid
resolved_json: { transactions: [...], goals: [...], patient_guid: ... }
ttl: 3600 seconds (1 hour — SR content is immutable after finalization)
```

### 10.4 Summary of gateway.pdhc Changes

| Change | File | Type |
|--------|------|------|
| Call request.pdhc `/internal/service-request/{guid}/context` | `services/report_service.py` | Modify |
| Call request.pdhc `/internal/grant/validate` | `services/report_service.py` | Modify |
| Call contract.pdhc `/fhir/Contract/{guid}/scope` | new `services/contract_scope_service.py` | New |
| Transaction-to-concept validation against scope | `services/report_service.py` | New |
| Observation enrichment from SR context | `services/report_service.py` | New |
| Cache SR context and contract scope in `guid_resolution_cache` | `services/report_service.py` | Modify |
| Accept minimal payload (remove org_guid, contract_guid from required body fields) | `api/provider.py` | Modify |
| Tests: reconstruction, scope validation, cache behavior | tests | New |

---

## 11) Implementation Order

```
Phase 1: contract.pdhc
  1.1  Add term[]/scope validation to ensure_contract_shape()
  1.2  Implement get_permitted_concepts() helper
  1.3  Add GET /fhir/Contract/{guid}/scope endpoint
  1.4  Tests
  1.5  Scope editor in admin UI (can be deferred)

Phase 2: request.pdhc
  2.1  Implement ContextService.get_sr_context()
  2.2  Add internal API blueprint with service key auth
  2.3  Add GET /internal/service-request/{guid}/context
  2.4  Add POST /internal/grant/validate
  2.5  Simplify report endpoint to accept minimal payload
  2.6  Tests

Phase 3: gateway.pdhc
  3.1  Add contract scope lookup + cache
  3.2  Add SR context lookup + cache
  3.3  Implement new validation chain (Section 10.1)
  3.4  Implement transaction-to-concept scope check
  3.5  Implement observation enrichment from SR context
  3.6  Accept minimal payload on report endpoint
  3.7  Tests + end-to-end integration test

Phase 4: provider.pdhc
  4.1  Simplify report submission — remove org_guid, contract_guid from body
  4.2  Update upstream_client.py and status_callback.py
  4.3  Tests
```

Each phase can be deployed independently. Phase 1 and 2 are additive (new endpoints, no breaking changes). Phase 3 switches the gateway to the new validation chain. Phase 4 simplifies the provider client.

---

## 12) Security Implications

| Change | Security Impact |
|--------|----------------|
| HMAC_SECRET stays on request.pdhc only (Option A) | Reduces secret distribution — gateway cannot forge grants |
| Internal service keys for gateway↔request.pdhc | New secret to manage, but scoped to internal traffic only |
| Contract scope validation | Prevents providers from submitting data for concepts outside their contract |
| Provider sends fewer fields | Smaller attack surface — less data to spoof or tamper with |
| Contract lookup is live | Revoked contracts take effect immediately, no stale-copy window |
