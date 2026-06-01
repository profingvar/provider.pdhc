"""Tests for RequestMapper."""
from app.services.request_mapper import RequestMapper
from app.models import InboundRequest


SAMPLE_UPSTREAM = {
    'request_guid': 'req-guid-001',
    'receipt_token': 'tok-upstream-001',
    'provider_guid': 'test-instance-guid',
    'provider_name': 'Test Provider Instance',
    'status': 'submitted',
    'provider_status': None,
    'created_at': '2026-03-20T10:00:00Z',
    'updated_at': '2026-03-20T10:00:00Z',
    'careplan': {
        'careplan_guid': 'cp-guid-001',
        'title': 'Blood Work Panel',
        'patient': {
            'patient_guid': 'pat-guid-001',
            'name': 'Test Patient',
        },
        'activities': [
            {
                'activity_guid': 'act-guid-001',
                'title': 'Complete Blood Count',
                'transactions': [
                    {
                        'transaction_guid': 'tx-guid-001',
                        'concept_guid': 'con-guid-001',
                        'concept_name': 'Hemoglobin',
                        'response_type': 'numeric',
                        'valueset_values': [],
                        'unit': 'g/dL',
                        'required': True,
                    }
                ],
            }
        ],
        'dispatch_metadata': {
            'dispatched_at': '2026-03-20T09:00:00+00:00',
            'due_at': '2026-03-21T09:00:00+00:00',
            'priority': 'urgent',
            'notes': 'Fasting required',
        },
    },
}


def test_to_inbound_request(app):
    with app.app_context():
        result = RequestMapper.to_inbound_request(SAMPLE_UPSTREAM, source_url='http://test/api/v1')
        assert result['request_guid'] == 'req-guid-001'
        assert result['provider_guid'] == 'test-instance-guid'
        assert result['receipt_token'] == 'tok-upstream-001'
        assert result['status'] == 'new'
        assert result['source_url'] == 'http://test/api/v1'
        assert len(result['checksum']) == 64
        assert result['careplan_json']['title'] == 'Blood Work Panel'


def test_to_provider_task(app):
    with app.app_context():
        result = RequestMapper.to_provider_task(SAMPLE_UPSTREAM)
        assert result['receipt_token'] == 'tok-upstream-001'
        assert result['provider_guid'] == 'test-instance-guid'
        assert result['request_guid'] == 'req-guid-001'
        assert result['status'] == 'dispatched'
        assert result['patient_guid'] == 'pat-guid-001'
        assert result['patient_name'] == 'Test Patient'
        assert result['careplan_guid'] == 'cp-guid-001'
        assert result['careplan_title'] == 'Blood Work Panel'
        assert result['priority'] == 'urgent'
        assert result['notes'] == 'Fasting required'
        assert result['dispatched_at'] is not None
        assert result['due_at'] is not None


def test_to_careplan_cache(app):
    with app.app_context():
        result = RequestMapper.to_careplan_cache(SAMPLE_UPSTREAM)
        assert result['receipt_token'] == 'tok-upstream-001'
        assert result['careplan_json']['careplan_guid'] == 'cp-guid-001'
        assert len(result['careplan_json']['activities']) == 1


def test_mapper_missing_optional_fields(app):
    with app.app_context():
        minimal = {
            'request_guid': 'req-minimal',
            'receipt_token': 'tok-minimal',
            'provider_guid': 'test-instance-guid',
            'provider_name': 'Test',
            'status': 'submitted',
            'careplan': {
                'careplan_guid': 'cp-min',
                'title': 'Minimal',
            },
        }
        task = RequestMapper.to_provider_task(minimal)
        assert task['patient_guid'] is None
        assert task['patient_name'] is None
        assert task['dispatched_at'] is None
        assert task['due_at'] is None
        assert task['priority'] == 'routine'
        assert task['notes'] is None

        inbound = RequestMapper.to_inbound_request(minimal)
        assert inbound['provider_status'] is None


def test_checksum_deterministic(app):
    with app.app_context():
        r1 = RequestMapper.to_inbound_request(SAMPLE_UPSTREAM)
        r2 = RequestMapper.to_inbound_request(SAMPLE_UPSTREAM)
        assert r1['checksum'] == r2['checksum']


def test_checksum_changes_on_different_data(app):
    with app.app_context():
        modified = dict(SAMPLE_UPSTREAM)
        modified['careplan'] = dict(SAMPLE_UPSTREAM['careplan'])
        modified['careplan']['title'] = 'Changed Title'

        r1 = RequestMapper.to_inbound_request(SAMPLE_UPSTREAM)
        r2 = RequestMapper.to_inbound_request(modified)
        assert r1['checksum'] != r2['checksum']
