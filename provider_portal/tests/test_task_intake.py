"""Tests for ProviderTaskIntakeService (2.b)"""
from app.models import ProviderTask
from app.extensions import db


def test_list_empty(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/my', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_get_task_not_found(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/nonexistent', headers=auth_headers)
    assert resp.status_code == 404


def test_get_task(client, provider, api_key, auth_headers, app):
    task = ProviderTask(
        receipt_token='tok-001',
        provider_guid=provider.guid,
        status='dispatched',
        patient_name='Test Patient',
    )
    db.session.add(task)
    db.session.commit()
    resp = client.get('/api/v1/provider-tasks/tok-001', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['receipt_token'] == 'tok-001'
    assert data['patient_name'] == 'Test Patient'


def test_list_with_status_filter(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='tok-a', provider_guid=provider.guid, status='dispatched'))
    db.session.add(ProviderTask(receipt_token='tok-b', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()
    resp = client.get('/api/v1/provider-tasks/my?status=dispatched', headers=auth_headers)
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['status'] == 'dispatched'


def test_list_with_limit(client, provider, api_key, auth_headers, app):
    for i in range(5):
        db.session.add(ProviderTask(receipt_token=f'tok-{i}', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()
    resp = client.get('/api/v1/provider-tasks/my?limit=3', headers=auth_headers)
    assert len(resp.get_json()) == 3
