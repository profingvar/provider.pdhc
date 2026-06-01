# Provider Widget Content — FHIR Packaging Design

**Date:** 2026-04-01
**Status:** Design — implementation deferred to analytics phase
**Scope:** How a provider packs visual/graphic content as FHIR resources for the CDR, to be consumed later by a patient dashboard

---

## 1) Problem

A provider completing a task may want to send not just structured observations (numbers, categories) but also visual content — a trend chart, an anatomical SVG, a summary graphic — intended for the patient to see on a dashboard. Today the report payload only carries observations. There is no mechanism for rich visual content that survives the trip through gateway.pdhc into the CDR.

---

## 2) Architectural Constraint

The visual content must travel the **existing data path**:

```
provider.pdhc
  → POST /api/v1/provider/report/{sr_guid}   (composite key auth)
  → gateway.pdhc
  → validates, resolves GUID chain, vectorizes
  → stores in CDR (inbound_observations + observation_vectors)
```

A future **patient dashboard module** (analytics phase) reads from the CDR and renders the widgets. The provider has no direct connection to the patient dashboard — the CDR is the intermediary.

---

## 3) FHIR Resource Mapping

FHIR R5 provides three resource types suited for visual content. All three can be included in `report_payload` alongside observations.

### 3.1 DiagnosticReport (container)

The `DiagnosticReport` resource wraps a provider's complete response: observations, conclusions, and **presentedForm** attachments. This is the natural container.

```json
{
  "resourceType": "DiagnosticReport",
  "status": "final",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "11502-2",
      "display": "Laboratory report"
    }]
  },
  "subject": { "reference": "Patient/<patient_guid>" },
  "result": [
    { "reference": "#obs-1" },
    { "reference": "#obs-2" }
  ],
  "presentedForm": [
    {
      "contentType": "image/svg+xml",
      "title": "Behandlingsöversikt — blodtryck 4 veckor",
      "data": "<base64-encoded SVG>"
    },
    {
      "contentType": "application/json",
      "title": "Blodtryckstrend",
      "data": "<base64-encoded chart descriptor JSON>"
    }
  ],
  "conclusion": "Blodtrycket har normaliserats under behandlingsperioden.",
  "contained": [
    { "resourceType": "Observation", "id": "obs-1", "..." : "..." },
    { "resourceType": "Observation", "id": "obs-2", "..." : "..." }
  ]
}
```

**Why DiagnosticReport?** It is the FHIR-standard way for a provider to deliver "results + visual presentation" as a unit. The `presentedForm` array is specifically designed for rendered/presentable content (PDFs, images, SVGs). The CDR stores the entire resource; the patient dashboard later extracts `presentedForm` entries for rendering.

### 3.2 Attachment Content Types

Each `presentedForm` entry is a FHIR `Attachment` with:

| contentType | Use | Size Guideline |
|-------------|-----|----------------|
| `image/svg+xml` | Vector graphics — diagrams, anatomical illustrations, progress visuals | < 500 KB |
| `image/png` | Raster graphics — photos, screenshots, complex renders | < 2 MB |
| `application/json` | Structured chart descriptor (see 3.3) — rendered by dashboard | < 100 KB |
| `text/html` | Formatted summary card (sanitized on ingest) | < 50 KB |
| `application/pdf` | Full report document | < 10 MB |

The `data` field carries base64-encoded content. The `title` field provides a human-readable label for the dashboard.

### 3.3 Chart Descriptor (application/json)

For dynamic charts, instead of a static image the provider sends a **chart descriptor** — structured data that the patient dashboard renders using its own chart library:

```json
{
  "widget_type": "chart",
  "chart_type": "line",
  "title": "Blodtryck senaste 4 veckor",
  "series": [
    {
      "label": "Systoliskt",
      "unit": "mmHg",
      "color": "#e74c3c",
      "data": [
        { "date": "2026-03-08", "value": 135 },
        { "date": "2026-03-15", "value": 128 },
        { "date": "2026-03-22", "value": 122 },
        { "date": "2026-03-29", "value": 118 }
      ]
    },
    {
      "label": "Diastoliskt",
      "unit": "mmHg",
      "color": "#3498db",
      "data": [
        { "date": "2026-03-08", "value": 88 },
        { "date": "2026-03-15", "value": 82 },
        { "date": "2026-03-22", "value": 78 },
        { "date": "2026-03-29", "value": 75 }
      ]
    }
  ],
  "reference_range": { "low": 60, "high": 140, "label": "Normalintervall" },
  "x_axis": "date",
  "y_axis": { "label": "mmHg", "min": 40, "max": 180 }
}
```

**Why data, not images?** A chart descriptor is safe by design (no script injection), accessible (screen readers can read the values), responsive (dashboard renders at any size), and interactive (tooltips, zoom). The gateway (gateway.pdhc) already has a Recharts-based chart system that can consume this format.

---

## 4) Report Payload Structure

The provider includes the DiagnosticReport in the existing `report_payload` field:

```json
POST /api/v1/provider/report/{sr_guid}
{
  "patient_guid": "...",
  "organisation_guid": "...",
  "grant_token": "...",
  "contract_guid": "...",
  "status": "completed",
  "report_payload": {
    "observations": [ ... ],
    "diagnostic_report": {
      "resourceType": "DiagnosticReport",
      "presentedForm": [ ... ],
      "conclusion": "...",
      "..."
    }
  }
}
```

No changes to the composite key auth, PAT validation, or grant token flow. The `report_payload` is already accepted as freeform JSON.

---

## 5) Gateway/CDR Storage

Gateway.pdhc stores the report as-is in `fhir_observation_json` (the full payload). During GUID chain resolution and vectorization (Phase 4 of gateway.pdhc), the vector context can include:

- The `conclusion` text (clinically meaningful, good for embedding)
- `presentedForm` metadata (contentType, title — not the base64 data itself)
- Observation values from `contained` or from the `observations` array

The base64 content in `presentedForm` is stored verbatim in the JSON column. The patient dashboard retrieves it via the gateway's query endpoints.

---

## 6) Patient Dashboard Rendering (Analytics Phase)

The patient dashboard module (future) reads from the CDR:

```
GET /api/v1/vectors/by-patient/{patient_guid}
  → returns observations + resolved context

GET /api/v1/observations/by-patient/{patient_guid}
  → returns raw inbound_observations with fhir_observation_json
  → dashboard extracts presentedForm entries
```

Rendering rules:

| contentType | Rendering |
|-------------|-----------|
| `image/svg+xml` | Decode base64, sanitize (strip scripts/event handlers), render in sandboxed `<div>` |
| `image/png` | Decode base64, render as `<img>` with CSP restrictions |
| `application/json` | Parse chart descriptor, render via chart library (Recharts) |
| `text/html` | Decode, sanitize via DOMPurify allowlist, render in sandboxed container |
| `application/pdf` | Offer as download link or embed in `<object>` tag |

---

## 7) Security Considerations

- **SVG sanitization** is critical — SVGs can contain `<script>`, `<foreignObject>`, `onclick`, and external resource references. Must be sanitized server-side at gateway ingest.
- **Size limits** enforced at gateway: reject `presentedForm` entries exceeding type-specific limits (see table in 3.2).
- **No external references** — all content must be self-contained (base64). No `<img src="https://...">` or `xlink:href` to external URLs. This prevents tracking pixels and dependency on provider uptime.
- **GDPR** — the visual content is patient data. Same audit trail and data_subject_guid tagging as observations.

---

## 8) What provider.pdhc Needs (Future)

When this is implemented:

1. **UI for composing presentedForm** — SVG upload, chart builder (series + dates + values), free text conclusion
2. **DiagnosticReport assembly** — wrap observations + presentedForm into FHIR DiagnosticReport
3. **Base64 encoding** — encode SVG/PNG/PDF before inclusion in payload
4. **Preview** — render the chart/SVG locally before submission so the provider sees what the patient will see

No changes needed to `upstream_client.py` or `status_callback.py` — the composite key report path already accepts arbitrary `report_payload` JSON.

---

## 9) Data Flow Summary

```
provider.pdhc                     gateway.pdhc / CDR              patient dashboard
    |                                  |                               |
    |  report_payload: {               |                               |
    |    observations: [...],          |                               |
    |    diagnostic_report: {          |                               |
    |      presentedForm: [            |                               |
    |        { SVG base64 },           |                               |
    |        { chart descriptor }      |                               |
    |      ],                          |                               |
    |      conclusion: "..."           |                               |
    |    }                             |                               |
    |  }                               |                               |
    |─────────────────────────────────>|                               |
    |  (PAT + composite key auth)      |                               |
    |                                  |  store in CDR                 |
    |                                  |  vectorize conclusion         |
    |                                  |  + observation context        |
    |                                  |                               |
    |                                  |  GET by-patient/<guid>        |
    |                                  |<──────────────────────────────|
    |                                  |  return observations +        |
    |                                  |  presentedForm attachments    |
    |                                  |──────────────────────────────>|
    |                                  |                               |
    |                                  |              render SVG/chart/HTML
    |                                  |              in patient view
```
