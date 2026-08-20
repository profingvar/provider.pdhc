"""Inbound push: patient_guid extraction from the SR subject.

request.pdhc dispatches the patient as a CONTAINED resource, so the SR
subject reference is "#patient-<guid>" rather than "Patient/<guid>". If we
fail to parse it, inbound.patient_guid stays NULL and the report-push guard
refuses to send observations to the gateway (regression seen on task
706b7880).
"""
from app.api.inbound import _process_push
from app.models import InboundRequest


def _sr(subject_ref, sr_id):
    return {
        'resourceType': 'ServiceRequest',
        'id': sr_id,
        'subject': {'reference': subject_ref, 'display': 'Per Bergström'},
        'contained': [
            {'resourceType': 'Patient', 'id': 'patient-abc-123',
             'name': [{'given': ['Per'], 'family': 'Bergström'}]},
        ],
    }


def test_contained_patient_reference_is_parsed(app):
    _process_push(_sr('#patient-abc-123', 'sr-1'), 'sr-1', 'grant-x')
    row = InboundRequest.query.filter_by(request_guid='sr-1').first()
    assert row is not None
    assert row.patient_guid == 'abc-123'


def test_plain_patient_reference_still_parsed(app):
    _process_push(_sr('Patient/def-456', 'sr-2'), 'sr-2', 'grant-x')
    row = InboundRequest.query.filter_by(request_guid='sr-2').first()
    assert row.patient_guid == 'def-456'
