"""Tests for StatusCallbackService — the gateway/request.pdhc router.

The critical invariant: a report with observation payload must NEVER be
sent to request.pdhc. request.pdhc's /provider/report endpoint will 200
OK and log report.received, but the observations themselves are silently
dropped. So when GATEWAY_SERVICE_URL is missing, the service must keep
the data local and log loudly — not fall back to request.pdhc.
"""
from unittest.mock import patch

from app.extensions import db
from app.models import InboundRequest
from app.services.status_callback import StatusCallbackService


def _make_inbound(receipt_token='rt-1', provider_guid='provider1',
                  with_grant=True, with_patient=True):
    inbound = InboundRequest(
        receipt_token=receipt_token,
        provider_guid=provider_guid,
        request_guid='sr-1',
        grant_token='grant-abc' if with_grant else None,
        patient_guid='p-001' if with_patient else None,
        contract_guid='c-1',
        organisation_guid='o-1',
        careplan_json={},
        checksum='deadbeef',
    )
    db.session.add(inbound)
    db.session.commit()
    return inbound


def test_report_with_payload_requires_gateway_url(app, caplog):
    """report_payload set + GATEWAY_SERVICE_URL missing → no upstream push,
    loud error log, data stays local."""
    _make_inbound()
    app.config['PROVIDER_TOKEN'] = 'pat-xyz'
    app.config['REQUEST_SERVICE_URL'] = 'https://request.pdhc.se'
    app.config['GATEWAY_SERVICE_URL'] = None  # the trap
    app.config['SSO_API_KEY'] = None

    with patch.object(StatusCallbackService, '_push_via_composite_key') as composite, \
         patch.object(StatusCallbackService, '_push_legacy') as legacy:
        with caplog.at_level('ERROR'):
            StatusCallbackService.push_status(
                'rt-1', 'provider1', 'completed',
                report_payload={'observations': [{'value': 7.2}]},
            )

        composite.assert_not_called()
        legacy.assert_not_called()
        assert any('GATEWAY_SERVICE_URL' in r.message for r in caplog.records)


def test_report_with_payload_uses_gateway_when_configured(app):
    """report_payload + full config → push goes to GATEWAY_SERVICE_URL,
    never to REQUEST_SERVICE_URL."""
    _make_inbound()
    app.config['PROVIDER_TOKEN'] = 'pat-xyz'
    app.config['REQUEST_SERVICE_URL'] = 'https://request.pdhc.se'
    app.config['GATEWAY_SERVICE_URL'] = 'https://gateway.pdhc.se'

    with patch.object(StatusCallbackService, '_push_via_composite_key') as composite:
        StatusCallbackService.push_status(
            'rt-1', 'provider1', 'completed',
            report_payload={'observations': [{'value': 7.2}]},
        )
        composite.assert_called_once()
        base_url_used = composite.call_args.args[0]
        assert base_url_used == 'https://gateway.pdhc.se'
        assert base_url_used != 'https://request.pdhc.se'


def test_status_only_still_routes_to_request_pdhc(app):
    """No payload → status-only push goes to request.pdhc as before."""
    _make_inbound()
    app.config['PROVIDER_TOKEN'] = 'pat-xyz'
    app.config['REQUEST_SERVICE_URL'] = 'https://request.pdhc.se'
    app.config['GATEWAY_SERVICE_URL'] = 'https://gateway.pdhc.se'

    with patch.object(StatusCallbackService, '_push_via_composite_key') as composite:
        StatusCallbackService.push_status(
            'rt-1', 'provider1', 'acknowledged',  # no report_payload
        )
        composite.assert_called_once()
        base_url_used = composite.call_args.args[0]
        assert base_url_used == 'https://request.pdhc.se'


def test_report_with_payload_blocked_when_grant_missing(app, caplog):
    """Missing grant_token also blocks the gateway push (loud) — no silent
    fall-through to request.pdhc."""
    _make_inbound(with_grant=False)
    app.config['PROVIDER_TOKEN'] = 'pat-xyz'
    app.config['REQUEST_SERVICE_URL'] = 'https://request.pdhc.se'
    app.config['GATEWAY_SERVICE_URL'] = 'https://gateway.pdhc.se'

    with patch.object(StatusCallbackService, '_push_via_composite_key') as composite:
        with caplog.at_level('ERROR'):
            StatusCallbackService.push_status(
                'rt-1', 'provider1', 'completed',
                report_payload={'observations': [{'value': 7.2}]},
            )
        composite.assert_not_called()
        assert any('grant_token' in r.message for r in caplog.records)
