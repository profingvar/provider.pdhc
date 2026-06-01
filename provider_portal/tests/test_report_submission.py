"""Tests for TaskReportSubmissionService (3.c)"""
from app.models import ProviderTask
from app.extensions import db


def test_submit_report(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='rpt-001', provider_guid=provider.guid, status='acknowledged')
    db.session.add(task)
    db.session.commit()

    resp = client.post(
        '/api/v1/provider-tasks/rpt-001/report',
        headers=auth_headers,
        json={
            'provider_payload': {'notes': 'All clear'},
            'notes': 'Provider notes',
            'receipt_message': 'Done',
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['task']['status'] == 'completed'
    assert data['receipt']['status'] == 'submitted'


def test_submit_report_idempotent(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='rpt-002', provider_guid=provider.guid, status='acknowledged')
    db.session.add(task)
    db.session.commit()

    payload = {'provider_payload': {'result': 'normal'}}
    client.post('/api/v1/provider-tasks/rpt-002/report', headers=auth_headers, json=payload)
    resp = client.post('/api/v1/provider-tasks/rpt-002/report', headers=auth_headers, json=payload)
    assert resp.status_code == 200


def test_submit_report_missing_payload(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='rpt-003', provider_guid=provider.guid, status='acknowledged')
    db.session.add(task)
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/rpt-003/report', headers=auth_headers, json={})
    assert resp.status_code == 400


def test_submit_report_not_found(client, provider, api_key, auth_headers):
    resp = client.post(
        '/api/v1/provider-tasks/nonexistent/report',
        headers=auth_headers,
        json={'provider_payload': {}},
    )
    assert resp.status_code == 404
