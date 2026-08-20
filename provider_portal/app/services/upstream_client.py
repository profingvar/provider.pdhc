"""HTTP client for request.pdhc API.

Supports both:
- PAT auth (X-Provider-Token) — new provider delivery endpoints
- SSO API key (X-API-Key) — legacy fallback
"""
import logging
import requests as http_requests
from ..errors import APIError

logger = logging.getLogger(__name__)


class UpstreamClient:

    def __init__(self, base_url, provider_token=None, api_key=None):
        self.base_url = base_url.rstrip('/')
        self.session = http_requests.Session()
        self.session.headers['Accept'] = 'application/json'

        # Prefer PAT over legacy API key
        if provider_token:
            self.session.headers['X-Provider-Token'] = provider_token
            self.auth_mode = 'pat'
        elif api_key:
            self.session.headers['X-API-Key'] = api_key
            self.auth_mode = 'legacy'
        else:
            self.auth_mode = 'none'

    # ── New provider delivery endpoints ──────────────────────

    def fetch_feed(self, since=None, limit=50):
        """Fetch metadata-only feed of ServiceRequests for this provider.

        Provider identity comes from the PAT — no provider_guid param needed.
        Returns list of items with download_url for each.
        """
        params = {'limit': min(limit, 200)}
        if since:
            params['since'] = since.isoformat() if hasattr(since, 'isoformat') else since

        url = f'{self.base_url}/provider/feed'
        logger.info('Fetching provider feed from %s', url)

        resp = self.session.get(url, params=params, timeout=30)
        self._check_response(resp, 'feed')
        return resp.json()

    def download_bundle(self, service_request_guid):
        """Download the full FHIR Bundle + grant_token for a ServiceRequest.

        Returns dict with: fhir_resource, grant_token, patient_guid,
        contract_guid, provider_org_guid, service_request_guid
        """
        url = f'{self.base_url}/provider/download/{service_request_guid}'
        logger.info('Downloading bundle for SR %s', service_request_guid)

        resp = self.session.get(url, timeout=30)
        self._check_response(resp, 'download')
        return resp.json()

    def submit_report(self, service_request_guid, patient_guid,
                      grant_token, status='completed', report_payload=None,
                      contract_guid=None, organisation_guid=None,
                      path=None):
        """Submit a report or status update via composite-key auth.

        Path selection:
        - For observation DATA → POST to `gateway.pdhc /provider/report/<sr>`
          (gateway writes inbound_observations after PAT+grant+SR validation).
        - For lifecycle status only → POST to
          `request.pdhc /provider/status/<sr>` (canonical; the old
          `/provider/report` on request.pdhc still works as a deprecation
          alias but logs a warning).

        Caller selects via `path`; defaults to `/provider/report` for the
        observation path since the most common caller is the gateway push.
        Status-only callers should pass `path='/provider/status'`.

        Required: patient_guid, grant_token, status.
        Gateway derives organisation_guid from PAT and contract_guid from grant.
        Optional contract_guid/organisation_guid are included for backward
        compat cross-checking only.
        """
        if path is None:
            path = '/provider/report'
        url = f'{self.base_url}{path}/{service_request_guid}'
        body = {
            'patient_guid': patient_guid,
            'grant_token': grant_token,
            'status': status,
        }
        # Include for backward compat cross-check if available
        if contract_guid:
            body['contract_guid'] = contract_guid
        if organisation_guid:
            body['organisation_guid'] = organisation_guid
        if report_payload:
            body['report_payload'] = report_payload

        logger.info('Submitting report for SR %s', service_request_guid)

        resp = self.session.post(url, json=body, timeout=30)
        self._check_response(resp, 'report')
        return resp.json()

    def ack_receipt(self, receipt_token):
        """Acknowledge a push delivery receipt."""
        url = f'{self.base_url}/provider/receipt/{receipt_token}/ack'
        resp = self.session.post(url, json={'status': 'acknowledged'}, timeout=30)
        self._check_response(resp, 'receipt_ack')
        return resp.json()

    # ── Legacy endpoints (fallback) ──────────────────────────

    def fetch_requests(self, provider_guid, since=None, cursor=None, count=100):
        """Legacy: Fetch requests from old /requests endpoint."""
        params = {
            'provider_guid': provider_guid,
            '_count': min(count, 500),
        }
        if since:
            params['since'] = since.isoformat() if hasattr(since, 'isoformat') else since
        if cursor:
            params['cursor'] = cursor

        url = f'{self.base_url}/requests'
        logger.info('Fetching requests (legacy) from %s params=%s', url, params)

        resp = self.session.get(url, params=params, timeout=30)
        self._check_response(resp, 'legacy_fetch')
        return resp.json()

    def push_status(self, request_guid, provider_guid, status):
        """Legacy: Push provider status back via old /requests endpoint."""
        url = f'{self.base_url}/requests/{request_guid}/status'
        resp = self.session.put(
            url,
            json={'provider_guid': provider_guid, 'status': status},
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info('Pushed status %s for request %s', status, request_guid)
            return resp.json()
        logger.warning(
            'Failed to push status %s for request %s: HTTP %d',
            status, request_guid, resp.status_code,
        )
        return None

    # ── Helpers ──────────────────────────────────────────────

    def _check_response(self, resp, operation):
        if resp.status_code in (200, 201, 202):
            return
        # Surface the upstream's ACTUAL error code + message rather than
        # collapsing every status into a generic label. A 403 from the
        # gateway may be GRANT_EXPIRED, SCOPE_VIOLATION, or a genuine
        # scope/permission denial — flattening them all to "insufficient
        # permissions" hides the real cause from the operator/provider.
        up_code, up_msg = None, None
        try:
            body = resp.json()
            if isinstance(body, dict):
                up_code = body.get('code') or body.get('error')
                up_msg = body.get('message')
        except Exception:
            pass
        detail = (f'{up_code}: {up_msg}' if up_code and up_msg
                  else (up_msg or up_code or (resp.text or '')[:200]))
        if resp.status_code == 401:
            raise APIError(
                f'Upstream auth failed on {operation}: {detail or "invalid token"}',
                code=up_code or 'UPSTREAM_AUTH_FAILED', status_code=502,
            )
        if resp.status_code == 403:
            raise APIError(
                f'Upstream denied {operation}: {detail or "forbidden"}',
                code=up_code or 'UPSTREAM_AUTH_DENIED', status_code=502,
            )
        raise APIError(
            f'Upstream error on {operation}: HTTP {resp.status_code}'
            + (f' — {detail}' if detail else ''),
            code=up_code or 'UPSTREAM_ERROR', status_code=502,
        )
