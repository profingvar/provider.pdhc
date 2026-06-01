"""Tests for gateway receipt ingestion endpoint and GatewayReceipt model."""
import pytest
from app.extensions import db
from app.models import GatewayReceipt, TaskAuditLog


class TestReceiptIngestEndpoint:

    def test_valid_receipt(self, client, app):
        """POST /api/v1/receipts/ingest with valid service key stores the receipt."""
        resp = client.post('/api/v1/receipts/ingest', json={
            'receipt_guid': 'rcpt-001',
            'service_request_guid': 'sr-001',
            'patient_guid': 'pat-001',
            'provider_org_guid': 'org-001',
            'contract_guid': 'ctr-001',
            'observations_stored': 3,
            'accepted_at': '2026-03-26T07:00:00Z',
            'payload_hash': 'abc123def456',
        }, headers={'X-Service-Key': 'test-gateway-key'})

        assert resp.status_code == 202
        data = resp.get_json()
        assert data['status'] == 'accepted'
        assert data['action'] == 'created'

        with app.app_context():
            receipt = GatewayReceipt.query.filter_by(receipt_guid='rcpt-001').first()
            assert receipt is not None
            assert receipt.service_request_guid == 'sr-001'
            assert receipt.observations_stored == 3
            assert receipt.payload_hash == 'abc123def456'

    def test_missing_service_key(self, client):
        """POST without X-Service-Key returns 401."""
        resp = client.post('/api/v1/receipts/ingest', json={
            'receipt_guid': 'rcpt-002',
            'service_request_guid': 'sr-002',
        })
        assert resp.status_code == 401

    def test_invalid_service_key(self, client):
        """POST with wrong X-Service-Key returns 401."""
        resp = client.post('/api/v1/receipts/ingest', json={
            'receipt_guid': 'rcpt-003',
            'service_request_guid': 'sr-003',
        }, headers={'X-Service-Key': 'wrong-key'})
        assert resp.status_code == 401

    def test_missing_required_fields(self, client):
        """POST without receipt_guid or service_request_guid returns 400."""
        resp = client.post('/api/v1/receipts/ingest', json={
            'patient_guid': 'pat-001',
        }, headers={'X-Service-Key': 'test-gateway-key'})
        assert resp.status_code == 400

    def test_duplicate_receipt(self, client, app):
        """Duplicate receipt_guid returns action=duplicate, no error."""
        payload = {
            'receipt_guid': 'rcpt-dup',
            'service_request_guid': 'sr-dup',
            'observations_stored': 1,
        }
        headers = {'X-Service-Key': 'test-gateway-key'}

        resp1 = client.post('/api/v1/receipts/ingest', json=payload, headers=headers)
        assert resp1.status_code == 202
        assert resp1.get_json()['action'] == 'created'

        resp2 = client.post('/api/v1/receipts/ingest', json=payload, headers=headers)
        assert resp2.status_code == 202
        assert resp2.get_json()['action'] == 'duplicate'

        with app.app_context():
            count = GatewayReceipt.query.filter_by(receipt_guid='rcpt-dup').count()
            assert count == 1

    def test_audit_log_created(self, client, app):
        """Receipt ingestion creates an audit log entry."""
        client.post('/api/v1/receipts/ingest', json={
            'receipt_guid': 'rcpt-audit',
            'service_request_guid': 'sr-audit',
            'observations_stored': 2,
        }, headers={'X-Service-Key': 'test-gateway-key'})

        with app.app_context():
            audit = TaskAuditLog.query.filter_by(
                receipt_token='sr-audit', action='gateway_receipt_ingested'
            ).first()
            assert audit is not None
            assert audit.payload_snapshot['observations_stored'] == 2


class TestPushReceiverMetaTags:

    def _make_bundle(self, **extra_tags):
        """Build a minimal FHIR Bundle with meta.tag entries."""
        tags = [
            {'system': 'https://pdhc.se/delivery', 'code': 'receipt_token', 'display': 'rt-100'},
            {'system': 'https://pdhc.se/delivery', 'code': 'grant_token', 'display': 'gt-abc'},
        ]
        for code, display in extra_tags.items():
            tags.append({'system': 'https://pdhc.se/delivery', 'code': code, 'display': display})

        return {
            'resourceType': 'Bundle',
            'type': 'message',
            'meta': {'tag': tags},
            'entry': [{
                'resource': {
                    'resourceType': 'ServiceRequest',
                    'id': 'sr-push-100',
                    'subject': {'reference': 'Patient/pat-push-100'},
                    'contained': [
                        {'resourceType': 'CarePlan', 'id': 'cp-1', 'title': 'Test Plan'},
                        {'resourceType': 'Patient', 'id': 'pat-push-100', 'name': [{'family': 'Test', 'given': ['User']}]},
                    ],
                },
            }],
        }

    def test_push_extracts_all_tags(self, client, app):
        """Push receiver extracts contract_guid, organisation_guid, expires_at from meta.tag."""
        from app.models import InboundRequest

        bundle = self._make_bundle(
            contract_guid='ctr-push-100',
            organisation_guid='org-push-100',
            expires_at='2026-04-15T12:00:00Z',
        )

        resp = client.post('/api/v1/inbound/push', json=bundle,
                           headers={'X-Push-Secret': 'test-push-secret'})
        assert resp.status_code == 202

        with app.app_context():
            inbound = InboundRequest.query.filter_by(request_guid='sr-push-100').first()
            assert inbound is not None
            assert inbound.grant_token == 'gt-abc'
            assert inbound.contract_guid == 'ctr-push-100'
            assert inbound.organisation_guid == 'org-push-100'
            assert inbound.grant_expires_at is not None

    def test_push_without_optional_tags(self, client, app):
        """Push works without contract_guid/organisation_guid/expires_at tags."""
        from app.models import InboundRequest

        bundle = self._make_bundle()
        # Use different SR id to avoid conflict
        bundle['entry'][0]['resource']['id'] = 'sr-push-200'

        resp = client.post('/api/v1/inbound/push', json=bundle,
                           headers={'X-Push-Secret': 'test-push-secret'})
        assert resp.status_code == 202

        with app.app_context():
            inbound = InboundRequest.query.filter_by(request_guid='sr-push-200').first()
            assert inbound is not None
            assert inbound.organisation_guid is None
            assert inbound.grant_expires_at is None
