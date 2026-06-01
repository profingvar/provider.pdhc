"""Tests for RequestSubscriptionService — both PAT (feed) and legacy (API key) paths."""
import json
from unittest.mock import patch, MagicMock
from app.services.subscription import RequestSubscriptionService
from app.models import InboundRequest, SyncState, ProviderTask, CarePlanCache, TaskAuditLog
from app.extensions import db


# ── Legacy test data helpers ─────────────────────────────

def _make_upstream_request(request_guid='req-001', receipt_token='tok-001',
                           provider_guid='test-instance-guid', title='Test Plan',
                           patient_name='Test Patient', provider_status=None):
    return {
        'request_guid': request_guid,
        'receipt_token': receipt_token,
        'provider_guid': provider_guid,
        'provider_name': 'Test Provider',
        'status': 'submitted',
        'provider_status': provider_status,
        'created_at': '2026-03-20T10:00:00Z',
        'updated_at': '2026-03-20T10:00:00Z',
        'careplan': {
            'careplan_guid': f'cp-{request_guid}',
            'title': title,
            'patient': {
                'patient_guid': f'pat-{request_guid}',
                'name': patient_name,
            },
            'activities': [],
            'dispatch_metadata': {
                'dispatched_at': '2026-03-20T09:00:00Z',
                'due_at': None,
                'priority': 'routine',
                'notes': None,
            },
        },
    }


def _mock_fetch(requests_list, has_more=False, cursor=None):
    return {
        'requests': requests_list,
        'has_more': has_more,
        'cursor': cursor,
    }


def _make_legacy_svc(app):
    """Create service in legacy mode (no PROVIDER_TOKEN)."""
    app.config['PROVIDER_TOKEN'] = None
    svc = RequestSubscriptionService(app=app)
    svc._client = MagicMock()
    return svc


# ── Feed test data helpers ───────────────────────────────

def _make_feed_item(sr_guid='sr-001', status='pending', title='Test Plan',
                    contract_guid='con-001'):
    return {
        'service_request_guid': sr_guid,
        'match_guid': f'match-{sr_guid}',
        'status': status,
        'title': title,
        'intent': 'order',
        'priority': 'routine',
        'contract_guid': contract_guid,
        'created_at': '2026-03-20T10:00:00Z',
        'updated_at': '2026-03-20T10:00:00Z',
        'download_url': f'/api/v1/provider/download/{sr_guid}',
    }


def _make_bundle_response(sr_guid='sr-001', patient_guid='pat-001',
                          contract_guid='con-001', title='Test Plan',
                          patient_name='Test Patient'):
    return {
        'service_request_guid': sr_guid,
        'patient_guid': patient_guid,
        'contract_guid': contract_guid,
        'provider_org_guid': 'test-instance-guid',
        'grant_token': f'grant-{sr_guid}',
        'fhir_resource': {
            'resourceType': 'ServiceRequest',
            'id': sr_guid,
            'priority': 'routine',
            'authoredOn': '2026-03-20T10:00:00Z',
            'contained': [
                {'resourceType': 'CarePlan', 'id': f'cp-{sr_guid}', 'title': title},
                {'resourceType': 'Patient', 'name': [{'given': [patient_name.split()[0]], 'family': patient_name.split()[-1]}]},
            ],
        },
    }


def _make_feed_svc(app):
    """Create service in feed mode (with PROVIDER_TOKEN)."""
    app.config['PROVIDER_TOKEN'] = 'test-provider-token'
    svc = RequestSubscriptionService(app=app)
    svc._client = MagicMock()
    return svc


# ── Feed-based sync tests ───────────────────────────────

def test_feed_sync_new_requests(app):
    with app.app_context():
        svc = _make_feed_svc(app)
        svc._client.fetch_feed.return_value = {'items': [_make_feed_item()]}
        svc._client.download_bundle.return_value = _make_bundle_response()

        new, updated, skipped = svc.sync()

        assert new == 1
        inbound = InboundRequest.query.filter_by(request_guid='sr-001').first()
        assert inbound is not None
        assert inbound.grant_token == 'grant-sr-001'
        assert inbound.patient_guid == 'pat-001'
        assert inbound.contract_guid == 'con-001'

        task = ProviderTask.query.filter_by(request_guid='sr-001').first()
        assert task is not None
        assert task.patient_name == 'Test Patient'


def test_feed_sync_unchanged_skipped(app):
    with app.app_context():
        svc = _make_feed_svc(app)
        svc._client.fetch_feed.return_value = {'items': [_make_feed_item()]}
        svc._client.download_bundle.return_value = _make_bundle_response()

        svc.sync()  # first sync

        svc._client.fetch_feed.return_value = {'items': [_make_feed_item()]}
        svc._client.download_bundle.return_value = _make_bundle_response()
        new, updated, skipped = svc.sync()

        assert new == 0
        assert skipped == 1


def test_feed_sync_updated_request(app):
    with app.app_context():
        svc = _make_feed_svc(app)
        svc._client.fetch_feed.return_value = {'items': [_make_feed_item()]}
        svc._client.download_bundle.return_value = _make_bundle_response()
        svc.sync()

        # Upstream changes the plan
        updated_bundle = _make_bundle_response(title='Updated Plan')
        updated_bundle['fhir_resource']['contained'][0]['title'] = 'Updated Plan'
        svc._client.fetch_feed.return_value = {'items': [_make_feed_item()]}
        svc._client.download_bundle.return_value = updated_bundle

        new, updated, skipped = svc.sync()
        assert updated == 1

        inbound = InboundRequest.query.filter_by(request_guid='sr-001').first()
        assert inbound.grant_token == 'grant-sr-001'


def test_feed_sync_download_failure_skips(app):
    with app.app_context():
        svc = _make_feed_svc(app)
        svc._client.fetch_feed.return_value = {'items': [
            _make_feed_item('sr-ok'),
            _make_feed_item('sr-fail'),
        ]}
        svc._client.download_bundle.side_effect = [
            _make_bundle_response('sr-ok'),
            Exception('Network error'),
        ]

        new, updated, skipped = svc.sync()
        assert new == 1  # sr-ok succeeded
        assert InboundRequest.query.filter_by(request_guid='sr-ok').count() == 1
        assert InboundRequest.query.filter_by(request_guid='sr-fail').count() == 0


def test_feed_sync_status(app):
    with app.app_context():
        svc = _make_feed_svc(app)
        status = svc.get_status()
        assert status['auth_mode'] == 'pat'


# ── Legacy sync tests ───────────────────────────────────

def test_sync_new_requests(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        upstream_data = _mock_fetch([_make_upstream_request()])
        svc._client.fetch_requests.return_value = upstream_data

        new, updated, skipped = svc.sync()

        assert new == 1
        assert updated == 0
        assert skipped == 0

        inbound = InboundRequest.query.filter_by(request_guid='req-001').first()
        assert inbound is not None
        assert inbound.receipt_token == 'tok-001'

        task = ProviderTask.query.filter_by(receipt_token='tok-001').first()
        assert task is not None
        assert task.patient_name == 'Test Patient'
        assert task.request_guid == 'req-001'

        cache = CarePlanCache.query.filter_by(receipt_token='tok-001').first()
        assert cache is not None

        audit = TaskAuditLog.query.filter_by(receipt_token='tok-001', action='sync').first()
        assert audit is not None
        assert audit.payload_snapshot['is_new'] is True


def test_sync_unchanged_skipped(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        req = _make_upstream_request()
        upstream_data = _mock_fetch([req])

        svc._client.fetch_requests.return_value = upstream_data
        svc.sync()  # first sync

        svc._client.fetch_requests.return_value = upstream_data
        new, updated, skipped = svc.sync()  # second sync, same data

        assert new == 0
        assert skipped == 1


def test_sync_updated_request(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        req = _make_upstream_request()

        svc._client.fetch_requests.return_value = _mock_fetch([req])
        svc.sync()

        # Acknowledge the task locally
        task = ProviderTask.query.filter_by(receipt_token='tok-001').first()
        task.status = 'acknowledged'
        db.session.commit()

        # Upstream careplan changes
        req_updated = _make_upstream_request(title='Updated Plan')
        svc._client.fetch_requests.return_value = _mock_fetch([req_updated])
        new, updated, skipped = svc.sync()

        assert updated == 1
        # Local task status should be preserved
        task = ProviderTask.query.filter_by(receipt_token='tok-001').first()
        assert task.status == 'acknowledged'

        # Careplan cache should be updated
        cache = CarePlanCache.query.filter_by(receipt_token='tok-001').first()
        assert cache.careplan_json['title'] == 'Updated Plan'


def test_sync_auth_failure(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        from app.errors import APIError
        svc._client.fetch_requests.side_effect = APIError(
            'Upstream auth failed', code='UPSTREAM_AUTH_FAILED', status_code=502
        )
        try:
            svc.sync()
        except APIError:
            pass

        state = SyncState.query.filter_by(provider_guid='test-instance-guid').first()
        assert state is not None
        assert state.last_error is not None
        assert 'auth' in state.last_error.lower()


def test_sync_network_error(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        svc._client.fetch_requests.side_effect = ConnectionError('Network unreachable')
        try:
            svc.sync()
        except ConnectionError:
            pass

        state = SyncState.query.filter_by(provider_guid='test-instance-guid').first()
        assert state.last_error is not None


def test_sync_duplicate_guid(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        req = _make_upstream_request()

        # Send same request twice in one batch
        svc._client.fetch_requests.return_value = _mock_fetch([req, req])
        # Second one will be skipped because request_guid already exists after first insert
        new, updated, skipped = svc.sync()

        assert new == 1
        assert InboundRequest.query.filter_by(request_guid='req-001').count() == 1


def test_sync_state_tracking(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        svc._client.fetch_requests.return_value = _mock_fetch(
            [_make_upstream_request()], cursor='cursor-abc'
        )
        svc.sync()

        state = SyncState.query.filter_by(provider_guid='test-instance-guid').first()
        assert state.last_sync_at is not None
        assert state.last_sync_cursor == 'cursor-abc'
        assert state.requests_synced == 1
        assert state.last_error is None


def test_sync_audit_trail(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        svc._client.fetch_requests.return_value = _mock_fetch([
            _make_upstream_request('req-a', 'tok-a'),
            _make_upstream_request('req-b', 'tok-b'),
        ])
        svc.sync()

        syncs = TaskAuditLog.query.filter_by(action='sync').all()
        assert len(syncs) == 2
        guids = {s.payload_snapshot['request_guid'] for s in syncs}
        assert guids == {'req-a', 'req-b'}


def test_provider_guid_mismatch(app):
    with app.app_context():
        svc = _make_legacy_svc(app)
        req = _make_upstream_request(provider_guid='wrong-guid')

        svc._client.fetch_requests.return_value = _mock_fetch([req])
        new, updated, skipped = svc.sync()

        assert new == 0
        assert InboundRequest.query.count() == 0


def test_sync_pagination(app):
    with app.app_context():
        svc = _make_legacy_svc(app)

        page1 = _mock_fetch(
            [_make_upstream_request('req-p1', 'tok-p1')],
            has_more=True, cursor='cursor-1',
        )
        page2 = _mock_fetch(
            [_make_upstream_request('req-p2', 'tok-p2')],
            has_more=False, cursor=None,
        )

        svc._client.fetch_requests.side_effect = [page1, page2]
        new, updated, skipped = svc.sync()

        assert new == 2
        assert InboundRequest.query.count() == 2
        assert ProviderTask.query.count() == 2


def test_get_status_configured(app):
    with app.app_context():
        app.config['PROVIDER_TOKEN'] = None
        svc = RequestSubscriptionService(app=app)
        status = svc.get_status()
        assert status['configured'] is True
        assert status['provider_guid'] == 'test-instance-guid'
        assert status['provider_name'] == 'Test Provider Instance'
        assert status['auth_mode'] == 'legacy'
        app.config['PROVIDER_TOKEN'] = 'test-provider-token'


def test_get_status_not_configured(app):
    with app.app_context():
        app.config['PROVIDER_GUID'] = None
        svc = RequestSubscriptionService(app=app)
        status = svc.get_status()
        assert status['configured'] is False
        app.config['PROVIDER_GUID'] = 'test-instance-guid'  # restore
