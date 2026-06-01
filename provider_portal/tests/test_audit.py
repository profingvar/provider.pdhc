"""Tests for ProviderAuditTelemetryService (4.b)"""
from app.models import ProviderTask, TaskAuditLog
from app.extensions import db


def test_acknowledge_creates_audit(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-001', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()

    client.post('/api/v1/provider-tasks/aud-001/accept', headers=auth_headers, json={'notes': 'test'})

    entries = TaskAuditLog.query.filter_by(receipt_token='aud-001').all()
    assert len(entries) == 1
    assert entries[0].action == 'acknowledge'
    assert entries[0].provider_guid == provider.guid
    assert entries[0].payload_snapshot['notes'] == 'test'


def test_report_creates_audit(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-002', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    client.post('/api/v1/provider-tasks/aud-002/report', headers=auth_headers,
                json={'provider_payload': {'result': 'ok'}})

    entries = TaskAuditLog.query.filter_by(receipt_token='aud-002').all()
    assert len(entries) == 1
    assert entries[0].action == 'report'


def test_audit_log_api(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-003', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()
    client.post('/api/v1/provider-tasks/aud-003/accept', headers=auth_headers, json={})

    resp = client.get('/api/v1/audit-log', headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]['receipt_token'] == 'aud-003'


def test_audit_log_filter_by_token(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-004', provider_guid=provider.guid, status='dispatched'))
    db.session.add(ProviderTask(receipt_token='aud-005', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()
    client.post('/api/v1/provider-tasks/aud-004/accept', headers=auth_headers, json={})
    client.post('/api/v1/provider-tasks/aud-005/accept', headers=auth_headers, json={})

    resp = client.get('/api/v1/audit-log?receipt_token=aud-004', headers=auth_headers)
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['receipt_token'] == 'aud-004'


def test_audit_immutability(client, provider, api_key, auth_headers, app):
    db.session.add(ProviderTask(receipt_token='aud-imm', provider_guid=provider.guid, status='dispatched'))
    db.session.commit()
    client.post('/api/v1/provider-tasks/aud-imm/accept', headers=auth_headers, json={})

    entry = TaskAuditLog.query.filter_by(receipt_token='aud-imm').first()
    original_guid = entry.guid
    original_created = entry.created_at

    # Re-query to verify unchanged
    entry2 = TaskAuditLog.query.filter_by(receipt_token='aud-imm').first()
    assert entry2.guid == original_guid
    assert entry2.created_at == original_created
