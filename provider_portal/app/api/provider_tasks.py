from flask import request, jsonify, g
from . import api_bp
from .auth import require_api_key
from ..services import (
    TaskIntakeService,
    AcknowledgementService,
    CarePlanDetailsService,
    GuidedResponseService,
    ReportSubmissionService,
    ReceiptService,
)
from ..errors import APIError


@api_bp.route('/provider-tasks/<receipt_token>', methods=['GET'])
@require_api_key(scope='read')
def get_task(receipt_token):
    task = TaskIntakeService.get_by_receipt_token(receipt_token, g.provider.guid)
    return jsonify(task.to_dict())


@api_bp.route('/provider-tasks/my', methods=['GET'])
@require_api_key(scope='read')
def list_my_tasks():
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    tasks = TaskIntakeService.list_tasks(g.provider.guid, status=status, limit=limit)
    return jsonify([t.to_dict() for t in tasks])


@api_bp.route('/provider-tasks/<receipt_token>/accept', methods=['POST'])
@require_api_key(scope='write')
def accept_task(receipt_token):
    data = request.get_json(silent=True) or {}
    task = AcknowledgementService.acknowledge(
        receipt_token, g.provider.guid, notes=data.get('notes')
    )
    return jsonify(task.to_dict())


@api_bp.route('/provider-tasks/<receipt_token>/report', methods=['POST'])
@require_api_key(scope='write')
def submit_report(receipt_token):
    data = request.get_json()
    if not data or 'provider_payload' not in data:
        raise APIError('provider_payload is required', code='VALIDATION_ERROR', status_code=400)

    provider_payload = data['provider_payload']

    # If guided mode with observations, validate against careplan
    if 'observations' in provider_payload:
        try:
            careplan = CarePlanDetailsService.get_details(receipt_token, g.provider.guid)
            transactions = []
            for activity in careplan.get('activity', []):
                pdhc_txns = activity.get('_pdhc_transactions', [])
                if pdhc_txns:
                    for tx in pdhc_txns:
                        entry = dict(tx)
                        entry.setdefault('transaction_guid', tx.get('concept_guid', ''))
                        transactions.append(entry)
                else:
                    detail = activity.get('detail', {})
                    for coding in detail.get('code', {}).get('coding', []):
                        transactions.append({
                            'transaction_guid': coding.get('code', ''),
                            'concept_guid': coding.get('code', ''),
                            'concept_name': coding.get('display', ''),
                            'requirement_type': 'required',
                        })
            GuidedResponseService.validate_observations(provider_payload['observations'], transactions)
        except APIError as e:
            if e.code == 'CAREPLAN_NOT_FOUND':
                pass  # allow submission without careplan validation
            else:
                raise

    task, receipt = ReportSubmissionService.submit(
        receipt_token=receipt_token,
        provider_guid=g.provider.guid,
        provider_payload=provider_payload,
        notes=data.get('notes'),
        receipt_message=data.get('receipt_message'),
    )
    return jsonify({
        'task': task.to_dict(),
        'receipt': receipt.to_dict(),
    })


@api_bp.route('/provider-tasks/<receipt_token>/careplan-details', methods=['GET'])
@require_api_key(scope='read')
def get_careplan_details(receipt_token):
    details = CarePlanDetailsService.get_details(receipt_token, g.provider.guid)
    return jsonify(details)


@api_bp.route('/provider-receipts', methods=['GET'])
@require_api_key(scope='read')
def list_receipts():
    receipt_token = request.args.get('receipt_token')
    limit = request.args.get('limit', 50, type=int)
    receipts = ReceiptService.get_receipts(
        g.provider.guid, receipt_token=receipt_token, limit=limit
    )
    return jsonify([r.to_dict() for r in receipts])
