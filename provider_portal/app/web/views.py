import os
from flask import render_template, request, flash, redirect, url_for, session, current_app, send_file, g
from . import web_bp
from ..models import Provider, ProviderTask, SubmissionReceipt, TaskAuditLog, SyncState, InboundRequest, GatewayReceipt
from ..services import AcknowledgementService, ReportSubmissionService
from ..errors import APIError
from pdhc_keyauth import login_required


def _get_provider_guid():
    """Return the provider GUID for this instance (from config)."""
    return current_app.config.get('PROVIDER_GUID')


@web_bp.route('/')
@login_required
def dashboard():
    pguid = _get_provider_guid()
    task_count = ProviderTask.query.filter_by(provider_guid=pguid).count() if pguid else 0
    pending_count = ProviderTask.query.filter_by(provider_guid=pguid, status='dispatched').count() if pguid else 0
    completed_count = ProviderTask.query.filter_by(provider_guid=pguid, status='completed').count() if pguid else 0
    receipt_count = SubmissionReceipt.query.filter_by(provider_guid=pguid).count() if pguid else 0
    gateway_receipt_count = GatewayReceipt.query.count()
    sync_status = None

    if pguid:
        state = SyncState.query.filter_by(provider_guid=pguid).first()
        sync_status = {
            'provider_name': current_app.config.get('PROVIDER_NAME', '—'),
            'provider_guid': pguid,
            'sync_enabled': current_app.config.get('SYNC_ENABLED', False),
            'last_sync_at': state.last_sync_at if state else None,
            'requests_synced': state.requests_synced if state else 0,
            'last_error': state.last_error if state else None,
            'inbound_count': InboundRequest.query.filter_by(provider_guid=pguid).count(),
        }

    return render_template('dashboard.html',
                           provider_name=current_app.config.get('PROVIDER_NAME', '—'),
                           task_count=task_count,
                           pending_count=pending_count,
                           completed_count=completed_count,
                           receipt_count=receipt_count,
                           gateway_receipt_count=gateway_receipt_count,
                           sync_status=sync_status)


@web_bp.route('/tasks')
@login_required
def task_list():
    pguid = _get_provider_guid()
    status_filter = request.args.get('status')
    query = ProviderTask.query.filter_by(provider_guid=pguid)
    if status_filter:
        query = query.filter_by(status=status_filter)
    tasks = query.order_by(ProviderTask.created_at.desc()).all()
    return render_template('tasks.html', tasks=tasks, status_filter=status_filter)


@web_bp.route('/tasks/<receipt_token>')
@login_required
def task_detail(receipt_token):
    from ..models import CarePlanCache
    pguid = _get_provider_guid()
    task = ProviderTask.query.filter_by(
        receipt_token=receipt_token, provider_guid=pguid
    ).first_or_404()
    audit_entries = TaskAuditLog.query.filter_by(
        receipt_token=receipt_token, provider_guid=pguid
    ).order_by(TaskAuditLog.created_at.desc()).all()
    inbound = InboundRequest.query.filter_by(
        receipt_token=receipt_token, provider_guid=pguid
    ).first()

    # Load careplan + goals for the detail view
    careplan = None
    goals_by_id = {}
    sr_notes = None
    cached = CarePlanCache.query.filter_by(receipt_token=receipt_token).first()
    if cached and cached.careplan_json:
        careplan = cached.careplan_json
    # Extract Goal resources and requester notes from the full FHIR resource
    if inbound and inbound.fhir_resource:
        fhir = inbound.fhir_resource
        for res in fhir.get('contained', []):
            if res.get('resourceType') == 'Goal':
                goals_by_id[res['id']] = res
        notes = fhir.get('note', [])
        if notes:
            sr_notes = notes[0].get('text', '')

    return render_template('task_detail.html', task=task,
                           audit_entries=audit_entries, inbound=inbound,
                           careplan=careplan, goals_by_id=goals_by_id,
                           sr_notes=sr_notes)


@web_bp.route('/tasks/<receipt_token>/accept', methods=['POST'])
@login_required
def accept_task(receipt_token):
    pguid = _get_provider_guid()
    notes = request.form.get('notes', '').strip() or None
    try:
        AcknowledgementService.acknowledge(receipt_token, pguid, notes=notes)
        flash('Task acknowledged', 'success')
    except APIError as e:
        flash(e.message, 'error')
    return redirect(url_for('web.task_detail', receipt_token=receipt_token))


@web_bp.route('/tasks/<receipt_token>/report', methods=['GET', 'POST'])
@login_required
def submit_report(receipt_token):
    pguid = _get_provider_guid()
    task = ProviderTask.query.filter_by(
        receipt_token=receipt_token, provider_guid=pguid
    ).first_or_404()

    # Extract transaction fields from the cached careplan for the guided form
    from ..models import CarePlanCache
    transactions = []
    cached = CarePlanCache.query.filter_by(receipt_token=receipt_token).first()
    if cached and cached.careplan_json:
        cp = cached.careplan_json
        for activity in cp.get('activity', []):
            activity_guid = activity.get('_pdhc_activity_guid', '')
            pdhc_txns = activity.get('_pdhc_transactions', [])
            if pdhc_txns:
                for tx in pdhc_txns:
                    transactions.append({
                        'transaction_guid': tx.get('transaction_guid', ''),
                        'activity_guid': tx.get('activity_guid', activity_guid),
                        'concept_guid': tx.get('concept_guid', ''),
                        'concept_name': tx.get('concept_name', ''),
                        'unit': tx.get('unit', ''),
                        'requirement_type': tx.get('requirement_type') or 'required',
                    })
            else:
                # Fallback: read from detail.code.coding
                detail = activity.get('detail', {})
                for coding in detail.get('code', {}).get('coding', []):
                    transactions.append({
                        'transaction_guid': coding.get('code', ''),
                        'activity_guid': activity_guid,
                        'concept_guid': coding.get('code', ''),
                        'concept_name': coding.get('display', ''),
                        'unit': '',
                        'requirement_type': 'required',
                    })

    if request.method == 'POST':
        import json
        from datetime import datetime as dt, timezone as tz

        # Check if this is a guided form submission (has obs_count)
        obs_count = request.form.get('obs_count')
        if obs_count:
            observations = []
            now_iso = dt.now(tz.utc).isoformat()
            for i in range(int(obs_count)):
                transaction_guid = request.form.get(f'transaction_guid_{i}', '')
                activity_guid = request.form.get(f'activity_guid_{i}', '')
                concept_guid = request.form.get(f'concept_guid_{i}', '')
                value_raw = request.form.get(f'value_{i}', '').strip()
                if not value_raw:
                    continue  # skip empty observations
                try:
                    value = float(value_raw)
                except ValueError:
                    value = value_raw
                obs = {
                    'transaction_guid': transaction_guid or concept_guid,
                    'activity_guid': activity_guid,
                    'concept_guid': concept_guid,
                    'value': value,
                    'recorded_at': now_iso,
                }
                obs_notes = request.form.get(f'notes_{i}', '').strip()
                if obs_notes:
                    obs['notes'] = obs_notes
                observations.append(obs)

            if not observations:
                flash('Please fill in at least one observation value', 'error')
                return render_template('report_form.html', task=task, transactions=transactions)

            provider_payload = {'observations': observations}
            notes = request.form.get('notes', '').strip() or None
            receipt_message = None
        else:
            # Manual JSON submission fallback
            payload_raw = request.form.get('provider_payload', '{}')
            notes = request.form.get('notes', '').strip() or None
            receipt_message = request.form.get('receipt_message', '').strip() or None
            try:
                provider_payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                flash('Invalid JSON payload', 'error')
                return render_template('report_form.html', task=task, transactions=transactions)

        try:
            _, receipt = ReportSubmissionService.submit(
                receipt_token=receipt_token,
                provider_guid=pguid,
                provider_payload=provider_payload,
                notes=notes,
                receipt_message=receipt_message,
            )
            flash('Report submitted', 'success')
            return redirect(url_for('web.task_detail', receipt_token=receipt_token))
        except APIError as e:
            flash(e.message, 'error')

    return render_template('report_form.html', task=task, transactions=transactions)


@web_bp.route('/receipts')
@login_required
def receipt_list():
    pguid = _get_provider_guid()
    receipts = SubmissionReceipt.query.filter_by(
        provider_guid=pguid
    ).order_by(SubmissionReceipt.submitted_at.desc()).all()
    return render_template('receipts.html', receipts=receipts)


@web_bp.route('/audit')
@login_required
def audit_log():
    pguid = _get_provider_guid()
    entries = TaskAuditLog.query.filter_by(
        provider_guid=pguid
    ).order_by(TaskAuditLog.created_at.desc()).limit(100).all()
    return render_template('audit.html', entries=entries)


@web_bp.route('/sync', methods=['POST'])
@login_required
def trigger_sync():
    from ..services.subscription import RequestSubscriptionService
    svc = RequestSubscriptionService(app=current_app._get_current_object())
    try:
        new, updated, skipped = svc.sync()
        flash(f'Sync complete: {new} new, {updated} updated, {skipped} unchanged', 'success')
    except Exception as e:
        flash(f'Sync failed: {e}', 'error')
    return redirect(url_for('web.dashboard'))


@web_bp.route('/gateway-receipts')
@login_required
def gateway_receipts():
    receipts = GatewayReceipt.query.order_by(GatewayReceipt.created_at.desc()).limit(200).all()
    return render_template('gateway_receipts.html', receipts=receipts)


@web_bp.route('/docs')
def docs_page():
    return render_template('docs.html')


@web_bp.route('/docs/download/<doc_name>')
def download_doc(doc_name):
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'docs')
    docs_dir = os.path.abspath(docs_dir)
    allowed = {
        'user-guide': 'provider_user_guide.md',
        'technical-guide': 'provider_technical_guide.md',
    }
    filename = allowed.get(doc_name)
    if not filename:
        flash('Document not found', 'error')
        return redirect(url_for('web.docs_page'))
    filepath = os.path.join(docs_dir, filename)
    if not os.path.isfile(filepath):
        flash('Document file not found on server', 'error')
        return redirect(url_for('web.docs_page'))
    return send_file(filepath, as_attachment=True, download_name=filename)
