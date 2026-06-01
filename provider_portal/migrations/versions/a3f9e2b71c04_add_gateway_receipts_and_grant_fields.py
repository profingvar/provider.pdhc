"""Add gateway_receipts table and inbound_request grant fields

Revision ID: a3f9e2b71c04
Revises: c08785713a09
Create Date: 2026-04-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f9e2b71c04'
down_revision = 'c08785713a09'
branch_labels = None
depends_on = None


def upgrade():
    # New table: gateway_receipts
    op.create_table('gateway_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guid', sa.String(length=36), nullable=False),
        sa.Column('receipt_guid', sa.String(length=36), nullable=False),
        sa.Column('service_request_guid', sa.String(length=36), nullable=False),
        sa.Column('patient_guid', sa.String(length=36), nullable=True),
        sa.Column('provider_org_guid', sa.String(length=36), nullable=True),
        sa.Column('contract_guid', sa.String(length=36), nullable=True),
        sa.Column('observations_stored', sa.Integer(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gateway_receipts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gateway_receipts_guid'), ['guid'], unique=True)
        batch_op.create_index(batch_op.f('ix_gateway_receipts_receipt_guid'), ['receipt_guid'], unique=True)
        batch_op.create_index(batch_op.f('ix_gateway_receipts_service_request_guid'), ['service_request_guid'], unique=False)
        batch_op.create_index(batch_op.f('ix_gateway_receipts_patient_guid'), ['patient_guid'], unique=False)

    # Add columns to inbound_requests
    with op.batch_alter_table('inbound_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organisation_guid', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('grant_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_inbound_requests_organisation_guid'), ['organisation_guid'], unique=False)


def downgrade():
    with op.batch_alter_table('inbound_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inbound_requests_organisation_guid'))
        batch_op.drop_column('grant_expires_at')
        batch_op.drop_column('organisation_guid')

    op.drop_table('gateway_receipts')
