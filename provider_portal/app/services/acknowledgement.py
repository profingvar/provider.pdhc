from datetime import datetime, timezone
from ..models import ProviderTask, TaskAuditLog
from ..extensions import db
from ..errors import APIError


class AcknowledgementService:

    @staticmethod
    def acknowledge(receipt_token, provider_guid, notes=None):
        task = ProviderTask.query.filter_by(
            receipt_token=receipt_token, provider_guid=provider_guid
        ).first()
        if not task:
            raise APIError('Task not found', code='TASK_NOT_FOUND', status_code=404)

        if task.status == 'acknowledged':
            return task  # idempotent

        if task.status not in ('dispatched',):
            raise APIError(
                f'Cannot acknowledge task in status: {task.status}',
                code='CONFLICT',
                status_code=409,
            )

        task.status = 'acknowledged'
        task.acknowledged_at = datetime.now(timezone.utc)
        if notes:
            task.notes = notes

        audit = TaskAuditLog(
            receipt_token=receipt_token,
            provider_guid=provider_guid,
            action='acknowledge',
            payload_snapshot={'notes': notes},
        )
        db.session.add(audit)
        db.session.commit()

        # Push status back to request.pdhc.se
        try:
            from .status_callback import StatusCallbackService
            StatusCallbackService.push_status(receipt_token, provider_guid, 'acknowledged')
        except Exception:
            pass  # don't fail the local operation if upstream push fails

        return task
