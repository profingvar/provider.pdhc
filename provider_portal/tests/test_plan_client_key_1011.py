"""#1011 — provider1's plan_client sends its read_only key to plan.pdhc.

plan gated its reads (stage 3 of #931). This client is FAIL-SOFT: any error
returns an empty map and the guided form degrades to text boxes, so a missing
or unsent key would look like a working form. These tests pin that every call
carries the pair, that an unset key is named in ONE warning, and that the
fail-soft still holds when plan refuses.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services import plan_client

PLANDEF = '11111111-1111-4111-8111-111111111111'
CONCEPT = '22222222-2222-4222-8222-222222222222'


@pytest.fixture(autouse=True)
def _fresh(app):
    plan_client._cache.clear()
    plan_client._warned_missing_key = False
    app.config['PLAN_BASE_URL'] = 'http://plan-test'
    app.config['PLAN_SOURCE_SERVICE'] = 'provider1.pdhc'
    app.config['PLAN_SERVICE_KEY'] = ''
    yield
    plan_client._cache.clear()


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f'{status}')
    else:
        r.raise_for_status.return_value = None
    return r


def _fake_plan(url, headers=None, timeout=None):
    """A plan that REFUSES without the key, like the gated one."""
    if (headers or {}).get('X-Service-Key') != 'k-1011':
        return _resp({'error': 'Authentication required'}, 401)
    if url.endswith(f'/plandefinitions/{PLANDEF}'):
        return _resp({'activities': [{'transactions': [
            {'concept_guid': CONCEPT, 'concept_unit_name': 'mmol/L'}]}]})
    if url.endswith('/lookup/response-types'):
        return _resp([{'guid': 'rt-num', 'response_type_name': 'Numerical'}])
    if url.endswith(f'/concepts/{CONCEPT}'):
        return _resp({'response_type': 'rt-num', 'range_low': 2, 'range_high': 20})
    return _resp({}, 404)


def test_every_call_sends_the_pair(app):
    app.config['PLAN_SERVICE_KEY'] = 'k-1011'
    with patch('app.services.plan_client.requests.get', side_effect=_fake_plan) as g:
        meta = plan_client.concept_form_meta(PLANDEF)
    assert meta[CONCEPT]['kind'] == 'number' and meta[CONCEPT]['unit'] == 'mmol/L'
    assert g.call_count == 3
    for call in g.call_args_list:
        assert call.kwargs['headers'] == {'X-Source-Service': 'provider1.pdhc',
                                          'X-Service-Key': 'k-1011'}


def test_CONTROL_without_the_key_plan_refuses_and_the_form_degrades(app):
    """The failure this ticket prevents, reproduced: same fake plan, no key."""
    with patch('app.services.plan_client.requests.get', side_effect=_fake_plan):
        assert plan_client.concept_form_meta(PLANDEF) == {}


def test_an_unset_key_sends_nothing_and_warns_once_by_name(app, caplog):
    with caplog.at_level(logging.WARNING, logger='app.services.plan_client'):
        assert plan_client.plan_read_headers() == {}
        assert plan_client.plan_read_headers() == {}
    lines = [r.getMessage() for r in caplog.records
             if 'PLAN_SERVICE_KEY' in r.getMessage()]
    assert len(lines) == 1, lines


def test_the_key_never_appears_in_a_log_line(app, caplog):
    app.config['PLAN_SERVICE_KEY'] = 'k-1011-secret'
    with caplog.at_level(logging.DEBUG), \
            patch('app.services.plan_client.requests.get',
                  side_effect=requests.ConnectionError('down')):
        plan_client.concept_form_meta(PLANDEF)
    assert 'k-1011-secret' not in caplog.text


def test_source_defaults_to_the_instance_name(app):
    app.config['PLAN_SERVICE_KEY'] = 'k'
    app.config['PLAN_SOURCE_SERVICE'] = ''
    assert plan_client.plan_read_headers()['X-Source-Service'] == 'provider1.pdhc'


def test_config_maps_both_variables():
    from config import Config
    assert Config.PLAN_SOURCE_SERVICE
    assert hasattr(Config, 'PLAN_SERVICE_KEY')
