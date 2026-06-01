"""Tests for security hardening (4.c)"""
from app.models import ApiKey
from app.extensions import db


def test_key_is_hashed(provider, api_key):
    assert api_key.key_hash != 'test-api-key'
    assert api_key.verify('test-api-key')
    assert not api_key.verify('wrong-key')


def test_revoked_key_rejected(client, provider, api_key, app):
    api_key.revoked = True
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'test-api-key'})
    assert resp.status_code == 401


def test_expired_key_rejected(client, provider, app):
    from datetime import datetime, timezone, timedelta
    key = ApiKey.create(
        provider_guid=provider.guid,
        raw_key='expired-key',
        scopes='read,write',
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.session.add(key)
    db.session.commit()

    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'expired-key'})
    assert resp.status_code == 401


def test_key_rotation_api(client, provider, api_key, auth_headers, app):
    resp = client.post(f'/api/v1/api-keys/{api_key.guid}/rotate', headers=auth_headers)
    assert resp.status_code == 201
    data = resp.get_json()
    assert 'key' in data
    assert data['old_key_guid'] == api_key.guid

    # Old key should be revoked
    db.session.refresh(api_key)
    assert api_key.revoked is True

    # New key should work
    new_headers = {'X-API-Key': data['key'], 'Content-Type': 'application/json'}
    resp = client.get('/api/v1/provider-tasks/my', headers=new_headers)
    assert resp.status_code == 200


def test_key_revocation_api(client, provider, api_key, auth_headers, app):
    # Create a second key first so we can still auth after revoking
    resp = client.post('/api/v1/api-keys', headers=auth_headers,
                       json={'scopes': 'read,write', 'label': 'backup'})
    assert resp.status_code == 201
    backup_key = resp.get_json()['key']

    # Revoke original
    resp = client.post(f'/api/v1/api-keys/{api_key.guid}/revoke',
                       headers={'X-API-Key': backup_key, 'Content-Type': 'application/json'})
    assert resp.status_code == 200

    # Old key should fail
    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'test-api-key'})
    assert resp.status_code == 401


def test_create_key_with_expiry(client, provider, api_key, auth_headers, app):
    resp = client.post('/api/v1/api-keys', headers=auth_headers,
                       json={'scopes': 'read', 'label': 'temp', 'expires_in_days': 30})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['expires_at'] is not None
    assert data['scopes'] == 'read'
