"""Pushes provider status/reports back to request.pdhc.

Uses composite key (PAT + 4 GUIDs + grant_token) for the new API,
with fallback to legacy status push for old-format requests.
"""
import logging
from flask import current_app
from ..models import ProviderTask, InboundRequest
from .upstream_client import UpstreamClient

logger = logging.getLogger(__name__)


class StatusCallbackService:

    @staticmethod
    def push_status(receipt_token, provider_guid, status, report_payload=None):
        """Push status to upstream. Uses composite key if grant_token available.

        Reports (with payload) are sent to GATEWAY_SERVICE_URL (gateway.pdhc)
        which does full context enrichment.
        Status-only updates (acknowledge etc.) go to REQUEST_SERVICE_URL
        (request.pdhc) since gateway's report endpoint requires a payload.
        """
        provider_token = current_app.config.get('PROVIDER_TOKEN')
        sso_key = current_app.config.get('SSO_API_KEY')
        gateway_url = current_app.config.get('GATEWAY_SERVICE_URL')
        request_url = current_app.config.get('REQUEST_SERVICE_URL')

        inbound = InboundRequest.query.filter_by(
            receipt_token=receipt_token, provider_guid=provider_guid
        ).first()
        if not inbound:
            return  # locally created task, nothing to push

        # Reports with payload → gateway for enrichment.
        # Status-only (acknowledge etc.) → request.pdhc.
        # IMPORTANT: never send observation payload to request.pdhc — request.pdhc's
        # /provider/report endpoint will 200 OK and log report.received, but the
        # observations will never land in inbound_observations. Silent data loss.
        if report_payload:
            missing = []
            if not provider_token:
                missing.append('PROVIDER_TOKEN')
            if not inbound.grant_token:
                missing.append('inbound.grant_token')
            if not inbound.patient_guid:
                missing.append('inbound.patient_guid')
            if not gateway_url:
                missing.append('GATEWAY_SERVICE_URL')
            if missing:
                logger.error(
                    'Cannot push report for %s to gateway — missing: %s. '
                    'Data kept local; will NOT fall back to request.pdhc '
                    '(that path discards observations).',
                    inbound.request_guid, ', '.join(missing),
                )
                return
            StatusCallbackService._push_via_composite_key(
                gateway_url, provider_token, inbound, provider_guid,
                status, report_payload, path='/provider/report',
            )
        elif provider_token and inbound.grant_token and inbound.patient_guid:
            # Status-only push to request.pdhc — canonical path is /provider/status.
            # request.pdhc keeps /provider/report as a deprecated alias.
            if request_url:
                StatusCallbackService._push_via_composite_key(
                    request_url, provider_token, inbound, provider_guid,
                    status, None, path='/provider/status',
                )
        elif sso_key:
            StatusCallbackService._push_legacy(
                request_url, sso_key, inbound, provider_guid, status,
            )

    @staticmethod
    def _push_via_composite_key(base_url, provider_token, inbound,
                                 provider_guid, status, report_payload=None,
                                 path='/provider/report'):
        """Submit report or status update via composite-key auth.

        `path` selects the URL: `/provider/report` for observation data
        (only valid on gateway.pdhc) or `/provider/status` for
        lifecycle-only updates to request.pdhc.

        Gateway derives org_guid from PAT and contract_guid from grant.
        We still pass them for backward-compat cross-checking.
        """
        try:
            client = UpstreamClient(base_url=base_url, provider_token=provider_token)
            result = client.submit_report(
                service_request_guid=inbound.request_guid,
                patient_guid=inbound.patient_guid,
                grant_token=inbound.grant_token,
                status=status,
                report_payload=report_payload,
                contract_guid=inbound.contract_guid,
                organisation_guid=inbound.organisation_guid,
                path=path,
            )
            if result:
                inbound.provider_status = status
                from ..extensions import db
                db.session.commit()
                logger.info('Submitted report for %s via composite key → %s',
                            inbound.request_guid, status)
        except Exception as e:
            logger.warning('Failed to submit report for %s: %s',
                           inbound.request_guid, str(e))

    @staticmethod
    def _push_legacy(base_url, sso_key, inbound, provider_guid, status):
        """Legacy: push simple status via PUT /requests/<guid>/status."""
        try:
            client = UpstreamClient(base_url=base_url, api_key=sso_key)
            result = client.push_status(
                request_guid=inbound.request_guid,
                provider_guid=provider_guid,
                status=status,
            )
            if result:
                inbound.provider_status = status
                from ..extensions import db
                db.session.commit()
                logger.info('Pushed status %s for %s to upstream (legacy)',
                            status, inbound.receipt_token)
        except Exception as e:
            logger.warning('Failed to push status to upstream for %s: %s',
                           inbound.request_guid, str(e))
