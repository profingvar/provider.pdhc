"""
Full API endpoint test script per capability statement (Rules 9/20).
Tests all endpoints from Section 6 of the spec.
Results stored in ./results/<timestamp>_results/ (Rule 11).
"""
import json
import os
from datetime import datetime, timezone
from app.models import ProviderTask, CarePlanCache
from app.extensions import db


RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')


def _save_result(test_name, response, extra=None):
    """Save test result to results directory with ISO-8601 timestamp."""
    now = datetime.now(timezone.utc)
    folder = os.path.join(RESULTS_DIR, now.strftime('%Y-%m-%dT%H-%M-%SZ_results'))
    os.makedirs(folder, exist_ok=True)
    result = {
        'test': test_name,
        'status_code': response.status_code,
        'response': response.get_json(silent=True),
        'timestamp': now.isoformat(),
    }
    if extra:
        result['extra'] = extra
    with open(os.path.join(folder, f'{test_name}.json'), 'w') as f:
        json.dump(result, f, indent=2, default=str)


# --- Endpoint: GET /api/v1/provider-tasks/{receipt_token} ---

def test_endpoint_get_task_success(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(
        receipt_token='e2e-001', provider_guid=provider.guid, status='dispatched',
        patient_name='E2E Patient', careplan_title='E2E Plan',
    ))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/e2e-001', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['receipt_token'] == 'e2e-001'
    assert data['patient_name'] == 'E2E Patient'
    _save_result('get_task_success', resp)


def test_endpoint_get_task_404(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/missing-token', headers=auth_headers)
    assert resp.status_code == 404
    _save_result('get_task_404', resp)


def test_endpoint_get_task_401(client):
    resp = client.get('/api/v1/provider-tasks/any-token')
    assert resp.status_code == 401
    _save_result('get_task_401', resp)


# --- Endpoint: GET /api/v1/provider-tasks/my ---

def test_endpoint_list_tasks_empty(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/my', headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)
    _save_result('list_tasks_empty', resp)


def test_endpoint_list_tasks_with_data(client, provider, api_key, auth_headers, app):
    for i in range(3):
        db.session.add(ProviderTask(
            receipt_token=f'list-{i}', provider_guid=provider.guid,
            status='dispatched' if i < 2 else 'completed',
        ))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/my', headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 3
    _save_result('list_tasks_with_data', resp)


def test_endpoint_list_tasks_filter(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='flt-1', provider_guid=provider.guid, status='dispatched'))
    db.session.add(ProviderTask(receipt_token='flt-2', provider_guid=provider.guid, status='completed'))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/my?status=completed', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(t['status'] == 'completed' for t in data)
    _save_result('list_tasks_filter', resp)


def test_endpoint_list_tasks_limit(client, provider, api_key, auth_headers, app):
    for i in range(10):
        db.session.add(ProviderTask(receipt_token=f'lim-{i}', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/my?limit=5', headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 5
    _save_result('list_tasks_limit', resp)


# --- Endpoint: POST /api/v1/provider-tasks/{receipt_token}/accept ---

def test_endpoint_accept_success(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='acc-e2e', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/acc-e2e/accept', headers=auth_headers,
                       json={'notes': 'Accepted via E2E'})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'acknowledged'
    _save_result('accept_success', resp)


def test_endpoint_accept_idempotent(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='acc-idem', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()

    client.post('/api/v1/provider-tasks/acc-idem/accept', headers=auth_headers, json={})
    resp = client.post('/api/v1/provider-tasks/acc-idem/accept', headers=auth_headers, json={})
    assert resp.status_code == 200
    _save_result('accept_idempotent', resp)


def test_endpoint_accept_conflict(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='acc-conf', provider_guid=provider.guid, status='completed'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/acc-conf/accept', headers=auth_headers, json={})
    assert resp.status_code == 409
    _save_result('accept_conflict', resp)


# --- Endpoint: POST /api/v1/provider-tasks/{receipt_token}/report ---

def test_endpoint_report_manual(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='rpt-manual', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/rpt-manual/report', headers=auth_headers,
                       json={'provider_payload': {'result': 'all normal'}, 'notes': 'Manual submit'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['task']['status'] == 'completed'
    assert data['receipt']['status'] == 'submitted'
    _save_result('report_manual', resp)


def test_endpoint_report_guided(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='rpt-guided', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/rpt-guided/report', headers=auth_headers,
                       json={
                           'provider_payload': {
                               'observations': [
                                   {'transaction_guid': 'tx-1', 'concept_guid': 'c-1',
                                    'value': 120, 'unit': 'mmHg'},
                               ]
                           },
                           'receipt_message': 'Guided submission',
                       })
    assert resp.status_code == 200
    _save_result('report_guided', resp)


def test_endpoint_report_idempotent(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='rpt-idem', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    payload = {'provider_payload': {'data': 'same'}}
    client.post('/api/v1/provider-tasks/rpt-idem/report', headers=auth_headers, json=payload)
    resp = client.post('/api/v1/provider-tasks/rpt-idem/report', headers=auth_headers, json=payload)
    assert resp.status_code == 200
    _save_result('report_idempotent', resp)


def test_endpoint_report_validation_400(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='rpt-400', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/rpt-400/report', headers=auth_headers, json={})
    assert resp.status_code == 400
    _save_result('report_validation_400', resp)


# --- Endpoint: GET /api/v1/provider-tasks/{receipt_token}/careplan-details ---

def test_endpoint_careplan_details_cached(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='cp-001', provider_guid=provider.guid, status='dispatched'))
    db.session.add(CarePlanCache(
        receipt_token='cp-001',
        careplan_json={
            'patient': {'name': 'Test'},
            'careplan': {'title': 'Test Plan'},
            'activities': [{'transactions': [
                {'transaction_guid': 'tx-1', 'concept_name': 'BP', 'required': True}
            ]}],
        }
    ))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/cp-001/careplan-details', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'activities' in data
    _save_result('careplan_details_cached', resp)


def test_endpoint_careplan_details_404(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='cp-404', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/cp-404/careplan-details', headers=auth_headers)
    assert resp.status_code == 404
    _save_result('careplan_details_404', resp)


# --- Endpoint: GET /api/v1/provider-receipts ---

def test_endpoint_list_receipts(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='rcpt-e2e', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()
    client.post('/api/v1/provider-tasks/rcpt-e2e/report', headers=auth_headers,
                json={'provider_payload': {'done': True}})

    resp = client.get('/api/v1/provider-receipts', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    _save_result('list_receipts', resp)


# --- Endpoint: GET /api/v1/audit-log ---

def test_endpoint_audit_log(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-e2e', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()
    client.post('/api/v1/provider-tasks/aud-e2e/accept', headers=auth_headers, json={})

    resp = client.get('/api/v1/audit-log', headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) >= 1
    _save_result('audit_log', resp)


# --- End-to-end flow: intake → acknowledge → report → receipt ---

def test_e2e_full_flow(client, provider, api_key, auth_headers, app):
    # 1. Create task
    db.session.add(ProviderTask(
        receipt_token='e2e-flow', provider_guid=provider.guid, status='dispatched',
        patient_name='Flow Patient', careplan_title='Flow Plan',
    ))
    db.session.commit()

    # 2. Fetch task
    resp = client.get('/api/v1/provider-tasks/e2e-flow', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'dispatched'

    # 3. List tasks
    resp = client.get('/api/v1/provider-tasks/my', headers=auth_headers)
    assert resp.status_code == 200
    assert any(t['receipt_token'] == 'e2e-flow' for t in resp.get_json())

    # 4. Acknowledge
    resp = client.post('/api/v1/provider-tasks/e2e-flow/accept', headers=auth_headers,
                       json={'notes': 'E2E ack'})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'acknowledged'

    # 5. Submit report
    resp = client.post('/api/v1/provider-tasks/e2e-flow/report', headers=auth_headers,
                       json={
                           'provider_payload': {'result': 'normal', 'observations': []},
                           'notes': 'E2E report',
                           'receipt_message': 'E2E done',
                       })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['task']['status'] == 'completed'
    assert data['receipt']['status'] == 'submitted'

    # 6. Check receipts
    resp = client.get('/api/v1/provider-receipts?receipt_token=e2e-flow', headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1

    # 7. Check audit log
    resp = client.get('/api/v1/audit-log?receipt_token=e2e-flow', headers=auth_headers)
    assert resp.status_code == 200
    entries = resp.get_json()
    actions = {e['action'] for e in entries}
    assert 'acknowledge' in actions
    assert 'report' in actions

    _save_result('e2e_full_flow', resp, extra={'actions': list(actions)})
