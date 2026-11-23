"""plan.pdhc client — resolves per-concept form metadata for the guided
report form (response widget kind, unit, limits, slider anchors, options).

plan.pdhc is the authority on a concept's response_type + unit + range;
the FHIR careplan the provider receives carries only concept code +
display. We fetch the plan definition (for unit + requirement_type) and
each concept (for response_type + limits + anchors + valueset), and map
the response_type to the SAME canonical vocab the gateway validates
against (see request.pdhc context_service._PLAN_RT_TO_GATEWAY), so the
JSON value types we emit match what gateway.ObservationValidator expects.

Fail-soft: any error returns an empty map so the form degrades to plain
text inputs rather than breaking submission.

Credential (#1011): plan's reads are gated, so every call sends
`plan_read_headers()` — this instance's read_only service key. That
fail-soft is exactly why the key matters: without it plan answers 401, the
map comes back empty, and the provider sees text boxes with no error. A
missing key is therefore logged ONCE, by name, instead of silently.
"""
import time
import logging

import requests
from flask import current_app

logger = logging.getLogger(__name__)

# plan.pdhc response_type_name (lower-cased) -> (widget kind, gateway
# canonical response_type). Value JSON type per canonical rt:
#   numeric -> float, boolean -> bool, categorical/text -> str.
_RT_MAP = {
    'numerical':       ('number',        'numeric'),
    'integer':         ('integer',       'numeric'),
    'slider':          ('slider',        'numeric'),
    'boolean':         ('boolean',       'boolean'),
    'single choice':   ('single_choice', 'categorical'),
    'multiple choice': ('multi_choice',  'categorical'),
    'free text':       ('text',          'text'),
    'text':            ('text',          'text'),
}

_cache = {}   # plandef_guid -> (ts, {concept_guid: meta})
_TTL = 300.0


def _base():
    return (current_app.config.get('PLAN_BASE_URL') or 'https://plan.pdhc.se').rstrip('/')


_warned_missing_key = False


def plan_read_headers():
    """X-Source-Service + X-Service-Key for plan.pdhc, or {} when unset.

    Same pair as request/dashboard/cdr after #931. Unset sends nothing rather
    than a blank key (plan would answer 403 to a named service with an empty
    key; 401 for no credential is the clearer refusal), and warns once.
    """
    global _warned_missing_key
    key = (current_app.config.get('PLAN_SERVICE_KEY') or '').strip()
    if not key:
        if not _warned_missing_key:
            _warned_missing_key = True
            logger.warning('plan_client: PLAN_SERVICE_KEY is not set, so plan.pdhc '
                           'will refuse these reads and guided forms degrade to '
                           'text inputs (#1011)')
        return {}
    src = (current_app.config.get('PLAN_SOURCE_SERVICE') or '').strip() or 'provider1.pdhc'
    return {'X-Source-Service': src, 'X-Service-Key': key}


def _get(path):
    r = requests.get(f"{_base()}/api/v1{path}", headers=plan_read_headers(), timeout=8)
    r.raise_for_status()
    return r.json()


def _unlist(payload):
    if isinstance(payload, dict) and 'items' in payload:
        return payload['items']
    return payload


def plandef_guid_from_careplan(careplan_json):
    """Pull the plan-definition guid out of a careplan's
    instantiatesCanonical (…/plandefinitions/<guid>). None if absent."""
    if not isinstance(careplan_json, dict):
        return None
    canon = careplan_json.get('instantiatesCanonical') or []
    if isinstance(canon, str):
        canon = [canon]
    for url in canon:
        if isinstance(url, str) and 'plandefinitions/' in url:
            return url.rstrip('/').split('plandefinitions/', 1)[1].split('/')[0].split('?')[0]
    return None


def concept_form_meta(plandef_guid):
    """{concept_guid: meta} for a plan definition, cached per plandef.

    meta = {kind, response_type, unit, min, max, step, anchor_low,
    anchor_high, options, requirement_type, display}. Empty dict on any
    failure (the form then falls back to plain text inputs)."""
    if not plandef_guid:
        return {}
    now = time.time()
    hit = _cache.get(plandef_guid)
    if hit and (now - hit[0]) < _TTL:
        return hit[1]
    try:
        meta = _build(plandef_guid)
    except Exception as e:  # noqa: BLE001 — fail-soft by design
        logger.warning('plan_client: form meta build failed for %s: %s', plandef_guid, e)
        meta = {}
    _cache[plandef_guid] = (now, meta)
    return meta


def _response_type_names():
    data = _unlist(_get('/lookup/response-types'))
    out = {}
    for r in (data or []):
        g = r.get('guid')
        if g:
            out[g] = (r.get('response_type_name') or '').strip().lower()
    return out


def _build(plandef_guid):
    plandef = _get(f'/plandefinitions/{plandef_guid}')
    rt_names = _response_type_names()

    txn_by_concept = {}
    for act in plandef.get('activities', []):
        for tx in act.get('transactions', []):
            cg = tx.get('concept_guid')
            if cg:
                txn_by_concept[cg] = tx

    meta = {}
    for cg, tx in txn_by_concept.items():
        try:
            c = _get(f'/concepts/{cg}')
        except Exception:  # noqa: BLE001
            c = {}
        rt_name = rt_names.get(c.get('response_type'), '')
        kind, canonical = _RT_MAP.get(rt_name, ('text', 'text'))
        step = 1 if kind == 'integer' else ('any' if kind in ('number', 'slider') else None)
        options = _value_options(c.get('valueset')) if kind in ('single_choice', 'multi_choice') else []
        meta[cg] = {
            'kind': kind,
            'response_type': canonical,
            'unit': tx.get('concept_unit_name') or '',
            'min': c.get('range_low'),
            'max': c.get('range_high'),
            'step': step,
            'anchor_low': c.get('anchor_low_text'),
            'anchor_high': c.get('anchor_high_text'),
            'options': options,
            'requirement_type': (tx.get('requirement_type') or 'required'),
            'display': c.get('concept_display_text') or tx.get('concept_name') or '',
        }
    return meta


def _value_options(valueset_guid):
    if not valueset_guid:
        return []
    try:
        vs = _get(f'/lookup/valuesets/{valueset_guid}')
        items = _unlist(vs.get('values') or vs.get('items') or vs)
        out = []
        for v in (items or []):
            code = v.get('guid') or v.get('code') or v.get('value_guid')
            label = (v.get('display_text') or v.get('value_name')
                     or v.get('name') or code)
            if code:
                out.append({'code': code, 'label': label})
        return out
    except Exception:  # noqa: BLE001
        return []
