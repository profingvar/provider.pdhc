"""Tests for error semantics (4.a)"""


def test_400_missing_payload(client, provider, api_key, auth_headers, app):
    from app.models import ProviderTask
    from app.extensions import db
    db.session.add(ProviderTask(receipt_token='err-001', provider_guid=provider.guid, status='acknowledged'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/err-001/report', headers=auth_headers, json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'code' in data
    assert 'message' in data


def test_401_missing_key(client):
    resp = client.get('/api/v1/provider-tasks/my')
    assert resp.status_code == 401
    data = resp.get_json()
    assert data['code'] == 'AUTH_MISSING'


def test_401_invalid_key(client):
    resp = client.get('/api/v1/provider-tasks/my', headers={'X-API-Key': 'bad'})
    assert resp.status_code == 401
    assert resp.get_json()['code'] == 'AUTH_INVALID'


def test_403_scope_mismatch(client, provider, app):
    from app.models import ApiKey
    from app.extensions import db
    key = ApiKey.create(provider_guid=provider.guid, raw_key='readonly', scopes='read')
    db.session.add(key)
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/x/accept',
                       headers={'X-API-Key': 'readonly', 'Content-Type': 'application/json'}, json={})
    assert resp.status_code == 403
    assert resp.get_json()['code'] == 'AUTH_SCOPE_MISMATCH'


def test_404_task_not_found(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/nonexistent', headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()['code'] == 'TASK_NOT_FOUND'


def test_409_acknowledge_conflict(client, provider, api_key, auth_headers, app):
    from app.models import ProviderTask
    from app.extensions import db
    db.session.add(ProviderTask(receipt_token='err-409', provider_guid=provider.guid, status='completed'))
    db.session.commit()

    resp = client.post('/api/v1/provider-tasks/err-409/accept', headers=auth_headers, json={})
    assert resp.status_code == 409
    assert resp.get_json()['code'] == 'CONFLICT'


def test_error_response_format(client, provider, api_key, auth_headers):
    resp = client.get('/api/v1/provider-tasks/does-not-exist', headers=auth_headers)
    data = resp.get_json()
    assert 'code' in data
    assert 'message' in data
    assert isinstance(data['code'], str)
    assert isinstance(data['message'], str)
