"""Tests for ProviderAccessSessionService (2.a)"""


def test_missing_api_key(client):
    resp = client.get('/api/v1/provider-tasks/my')
    assert resp.status_code == 401
    assert resp.get_json()['code'] == 'AUTH_MISSING'


def test_invalid_api_key(client):
    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'wrong-key'})
    assert resp.status_code == 401
    assert resp.get_json()['code'] == 'AUTH_INVALID'


def test_valid_api_key(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/my', headers=auth_headers)
    assert resp.status_code == 200


def test_revoked_key(client, provider, api_key, app):
    from app.extensions import db
    api_key.revoked = True
    db.session.commit()
    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'test-api-key'})
    assert resp.status_code == 401


def test_scope_mismatch(client, provider, app):
    from app.models import ApiKey
    from app.extensions import db
    key = ApiKey.create(
        provider_guid=provider.guid,
        raw_key='read-only-key',
        scopes='read',
        label='readonly',
    )
    db.session.add(key)
    db.session.commit()
    resp = client.post(
        '/api/v1/provider-tasks/token-123/accept',
        headers={'X-API-Key': 'read-only-key', 'Content-Type': 'application/json'},
        json={},
    )
    assert resp.status_code == 403
    assert resp.get_json()['code'] == 'AUTH_SCOPE_MISMATCH'
