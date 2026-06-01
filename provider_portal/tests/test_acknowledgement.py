"""Tests for TaskAcknowledgementService (2.d)"""
from app.models import ProviderTask
from app.extensions import db


def test_acknowledge_task(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='ack-001', provider_guid=provider.guid, status='dispatched')
    db.session.add(task)
    db.session.commit()

    resp = client.post(
        '/api/v1/provider-tasks/ack-001/accept',
        headers=auth_headers,
        json={'notes': 'Accepted by provider'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'acknowledged'
    assert data['acknowledged_at'] is not None


def test_acknowledge_idempotent(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='ack-002', provider_guid=provider.guid, status='dispatched')
    db.session.add(task)
    db.session.commit()

    client.post('/api/v1/provider-tasks/ack-002/accept', headers=auth_headers, json={})
    resp = client.post('/api/v1/provider-tasks/ack-002/accept', headers=auth_headers, json={})
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'acknowledged'


def test_acknowledge_completed_task_conflict(client, provider, api_key, auth_headers, app):
    task = ProviderTask(receipt_token='ack-003', provider_guid=provider.guid, status='completed')
    db.session.add(task)
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/ack-003/accept', headers=auth_headers, json={})
    assert resp.status_code == 409


def test_acknowledge_not_found(client, provider, api_key, auth_headers):
    resp = client.post('/api/v1/provider-tasks/nonexistent/accept', headers=auth_headers, json={})
    assert resp.status_code == 404
