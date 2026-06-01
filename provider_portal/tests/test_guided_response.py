"""Tests for GuidedResponseComposerService (3.b)"""
import pytest
from app.services import GuidedResponseService
from app.errors import APIError


TRANSACTIONS = [
    {
        'transaction_guid': 'tx-001',
        'concept_guid': 'c-001',
        'concept_name': 'Blood Pressure',
        'response_type': 'numeric',
        'required': True,
    },
    {
        'transaction_guid': 'tx-002',
        'concept_guid': 'c-002',
        'concept_name': 'Pain Level',
        'response_type': 'categorical',
        'valueset_values': ['none', 'mild', 'moderate', 'severe'],
        'required': True,
    },
    {
        'transaction_guid': 'tx-003',
        'concept_guid': 'c-003',
        'concept_name': 'Notes',
        'response_type': 'text',
        'required': False,
    },
]


def test_valid_observations(app):
    with app.app_context():
        observations = [
            {'transaction_guid': 'tx-001', 'value': 120, 'unit': 'mmHg'},
            {'transaction_guid': 'tx-002', 'value': 'mild'},
        ]
        GuidedResponseService.validate_observations(observations, TRANSACTIONS)


def test_missing_required(app):
    with app.app_context():
        observations = [
            {'transaction_guid': 'tx-002', 'value': 'mild'},
        ]
        with pytest.raises(APIError) as exc_info:
            GuidedResponseService.validate_observations(observations, TRANSACTIONS)
        assert exc_info.value.status_code == 422
        assert any(d['transaction_guid'] == 'tx-001' for d in exc_info.value.details)


def test_invalid_categorical(app):
    with app.app_context():
        observations = [
            {'transaction_guid': 'tx-001', 'value': 120},
            {'transaction_guid': 'tx-002', 'value': 'extreme'},
        ]
        with pytest.raises(APIError) as exc_info:
            GuidedResponseService.validate_observations(observations, TRANSACTIONS)
        assert exc_info.value.status_code == 422


def test_build_payload(app):
    with app.app_context():
        observations = [
            {'transaction_guid': 'tx-001', 'value': 120, 'notes': 'Test note'},
        ]
        result = GuidedResponseService.build_payload(observations)
        assert len(result['observations']) == 1
        obs = result['observations'][0]
        assert obs['transaction_guid'] == 'tx-001'
        assert obs['value'] == 120
        assert obs['notes'] == 'Test note'
        assert obs['recorded_at'] is not None
        # Gateway derives these — provider should NOT send them
        assert 'concept_guid' not in obs
        assert 'unit' not in obs


def test_build_payload_minimal(app):
    """Payload without notes omits the field entirely."""
    with app.app_context():
        observations = [
            {'transaction_guid': 'tx-001', 'value': 120},
        ]
        result = GuidedResponseService.build_payload(observations)
        obs = result['observations'][0]
        assert 'notes' not in obs
