# Changed Files

| File | Action | Date |
|------|--------|------|
| provider_portal/docker-compose.yml | Ticket #76: pinned `127.0.0.1:` on 9070/9071 so app/db ports are localhost-only (were binding to 0.0.0.0 → LAN-exposed via colima ssh-mux). Containers recreated; LAN refuses; https://provider1.pdhc.se/api/v1/health returns 200. | 2026-04-16 |
| readme.md | Created | 2026-03-20 |
| progress.md | Created/Updated | 2026-03-20 |
| changed_files.md | Created/Updated | 2026-03-20 |
| start.sh | Created | 2026-03-20 |
| safe_restart.sh | Created | 2026-03-20 |
| provider_portal/CLAUDE.md | Created | 2026-03-20 |
| provider_portal/requirements.txt | Created | 2026-03-20 |
| provider_portal/.env | Created | 2026-03-20 |
| provider_portal/.env.production | Created | 2026-03-20 |
| provider_portal/config.py | Created | 2026-03-20 |
| provider_portal/Dockerfile | Created | 2026-03-20 |
| provider_portal/docker-compose.yml | Created | 2026-03-20 |
| provider_portal/static/css/pdhc.css | Copied | 2026-03-20 |
| provider_portal/app/__init__.py | Created | 2026-03-20 |
| provider_portal/app/extensions.py | Created | 2026-03-20 |
| provider_portal/app/errors.py | Created/Updated | 2026-03-20 |
| provider_portal/app/models/__init__.py | Created | 2026-03-20 |
| provider_portal/app/models/provider.py | Created | 2026-03-20 |
| provider_portal/app/models/api_key.py | Created/Updated | 2026-03-20 |
| provider_portal/app/models/provider_task.py | Created | 2026-03-20 |
| provider_portal/app/models/task_audit_log.py | Created | 2026-03-20 |
| provider_portal/app/models/submission_receipt.py | Created | 2026-03-20 |
| provider_portal/app/models/careplan_cache.py | Created/Updated | 2026-03-20 |
| provider_portal/app/services/__init__.py | Created | 2026-03-20 |
| provider_portal/app/services/access_session.py | Created | 2026-03-20 |
| provider_portal/app/services/task_intake.py | Created | 2026-03-20 |
| provider_portal/app/services/queue_management.py | Created | 2026-03-20 |
| provider_portal/app/services/acknowledgement.py | Created | 2026-03-20 |
| provider_portal/app/services/careplan_details.py | Created | 2026-03-20 |
| provider_portal/app/services/guided_response.py | Created | 2026-03-20 |
| provider_portal/app/services/report_submission.py | Created | 2026-03-20 |
| provider_portal/app/services/receipt.py | Created | 2026-03-20 |
| provider_portal/app/api/__init__.py | Created/Updated | 2026-03-20 |
| provider_portal/app/api/auth.py | Created | 2026-03-20 |
| provider_portal/app/api/provider_tasks.py | Created | 2026-03-20 |
| provider_portal/app/api/audit.py | Created | 2026-03-20 |
| provider_portal/app/api/keys.py | Created | 2026-03-20 |
| provider_portal/app/web/__init__.py | Created | 2026-03-20 |
| provider_portal/app/web/views.py | Created/Updated | 2026-03-20 |
| provider_portal/templates/base.html | Created/Updated | 2026-03-20 |
| provider_portal/templates/dashboard.html | Created/Updated | 2026-03-20 |
| provider_portal/templates/login.html | Created | 2026-03-20 |
| provider_portal/templates/tasks.html | Created | 2026-03-20 |
| provider_portal/templates/task_detail.html | Created | 2026-03-20 |
| provider_portal/templates/report_form.html | Created | 2026-03-20 |
| provider_portal/templates/receipts.html | Created | 2026-03-20 |
| provider_portal/templates/audit.html | Created | 2026-03-20 |
| provider_portal/templates/404.html | Created | 2026-03-20 |
| provider_portal/docs/api_contract.md | Created | 2026-03-20 |
| provider_portal/docs/auth_scope_matrix.md | Created | 2026-03-20 |
| provider_portal/docs/operational_runbook.md | Created | 2026-03-20 |
| provider_portal/tests/__init__.py | Created | 2026-03-20 |
| provider_portal/tests/conftest.py | Created/Updated | 2026-03-20 |
| provider_portal/tests/test_auth.py | Created/Updated | 2026-03-20 |
| provider_portal/tests/test_task_intake.py | Created/Updated | 2026-03-20 |
| provider_portal/tests/test_acknowledgement.py | Created/Updated | 2026-03-20 |
| provider_portal/tests/test_report_submission.py | Created/Updated | 2026-03-20 |
| provider_portal/tests/test_guided_response.py | Created | 2026-03-20 |
| provider_portal/tests/test_error_handling.py | Created | 2026-03-20 |
| provider_portal/tests/test_audit.py | Created | 2026-03-20 |
| provider_portal/tests/test_security.py | Created | 2026-03-20 |
| provider_portal/tests/test_all_endpoints.py | Created | 2026-03-20 |
| provider_portal/config.py | Modified — added PROVIDER_TOKEN, PUSH_SECRET | 2026-03-24 |
| provider_portal/app/models/inbound_request.py | Modified — added fhir_resource, patient_guid, contract_guid, grant_token columns | 2026-03-24 |
| provider_portal/app/services/upstream_client.py | Rewritten — PAT auth, feed/download/report/ack methods + legacy kept | 2026-03-24 |
| provider_portal/app/services/subscription.py | Rewritten — two-path sync: feed (PAT) vs legacy (API key) | 2026-03-24 |
| provider_portal/app/services/request_mapper.py | Updated — added from_feed_item(), from_downloaded_bundle() for FHIR format | 2026-03-24 |
| provider_portal/app/services/status_callback.py | Rewritten — composite key report submission + legacy fallback | 2026-03-24 |
| provider_portal/app/services/report_submission.py | Modified — passes report_payload to upstream callback | 2026-03-24 |
| provider_portal/app/api/__init__.py | Modified — registered inbound module | 2026-03-24 |
| provider_portal/app/api/inbound.py | Created — push receiver: POST /inbound/push with X-Push-Secret validation | 2026-03-24 |
| provider_portal/app/web/views.py | Modified — added /docs page and /docs/download routes | 2026-03-24 |
| provider_portal/templates/base.html | Modified — added Docs nav link (logged in + logged out) | 2026-03-24 |
| provider_portal/templates/docs.html | Created — documentation download page | 2026-03-24 |
| docs/provider_user_guide.md | Created — non-technical user guide for providers | 2026-03-24 |
| docs/provider_technical_guide.md | Created — technical integration guide (API, auth, FHIR, security) | 2026-03-24 |
| provider_portal/tests/test_subscription.py | Updated — added 5 feed-based tests, legacy tests use _make_legacy_svc() | 2026-03-24 |
| provider_portal/app/models/inbound_request.py | Modified — added organisation_guid, grant_expires_at columns | 2026-04-01 |
| provider_portal/app/models/gateway_receipt.py | Created — GatewayReceipt model for observation receipts from gateway.pdhc | 2026-04-01 |
| provider_portal/app/models/__init__.py | Modified — registered GatewayReceipt | 2026-04-01 |
| provider_portal/app/api/receipts.py | Created — POST /receipts/ingest endpoint for gateway receipt ingestion | 2026-04-01 |
| provider_portal/app/api/__init__.py | Modified — registered receipts module | 2026-04-01 |
| provider_portal/app/api/inbound.py | Modified — extended meta.tag extraction (contract_guid, organisation_guid, expires_at) | 2026-04-01 |
| provider_portal/config.py | Modified — added GATEWAY_SERVICE_KEY | 2026-04-01 |
| provider_portal/app/web/views.py | Modified — added gateway_receipts page and count to dashboard | 2026-04-01 |
| provider_portal/templates/base.html | Modified — added Gateway nav link | 2026-04-01 |
| provider_portal/templates/dashboard.html | Modified — added Gateway Receipts card | 2026-04-01 |
| provider_portal/templates/gateway_receipts.html | Created — gateway receipts list page | 2026-04-01 |
| provider_portal/migrations/versions/a3f9e2b71c04_add_gateway_receipts_and_grant_fields.py | Created — migration for gateway_receipts table + inbound_requests grant columns | 2026-04-01 |
| provider_portal/tests/test_gateway_receipts.py | Created — 8 tests for receipts ingest + push meta.tag extraction | 2026-04-01 |
| provider_portal/docs/api_contract.md | Updated — added inbound/push and receipts/ingest endpoint docs | 2026-04-01 |
| provider_portal/docs/auth_scope_matrix.md | Updated — added push and gateway service key auth rules | 2026-04-01 |
| progress.md | Updated — Phase 7 results | 2026-04-01 |
| changed_files.md | Updated | 2026-04-01 |
| docs/widget_content_design.md | Created — FHIR packaging design for provider visual content to CDR/patient dashboard | 2026-04-01 |
| docs/data_package_reference.md | Created — Inbound/outbound data package reference with ** marking for echoed fields | 2026-04-02 |
| docs/data_package_reference.md | Revised — added Sections 8-12: reform specs for contract.pdhc, request.pdhc, gateway.pdhc | 2026-04-02 |
| docs/data_package_reference.docx | Regenerated — Word version with reform sections | 2026-04-02 |
| docs/data_package_reference.md | Revised — added resolvable contract URLs, two-list scope (request_scope + return_scope), vocabulary API reference | 2026-04-02 |
| docs/data_package_reference.docx | Regenerated — Word version with latest revisions | 2026-04-02 |
| provider_portal/migrations/versions/c08785713a09_initial_migration.py | Fixed — added missing create_table for inbound_requests (#65) | 2026-04-16 |
| provider_portal/.env | Quoted PROVIDER_NAME value with space so bash source doesn't fail | 2026-04-16 |
| start.sh | Split DB port (9071) out of APP_PORTS kill list — killing it broke colima docker tunnel; added OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES for gunicorn forks on macOS | 2026-04-16 |
| provider_portal/app/__init__.py | Ticket #70 — /api/v1/health adds Access-Control-Allow-Origin https://www.pdhc.se + Methods GET + Vary: Origin + Cache-Control: no-store so services.html can use mode:'cors'. Local was stale: pulled server version first (had ticket 7 reconcile + ticket 9 Stockholm filter), then added CORS. | 2026-04-16 |
| provider_portal/app/services/status_callback.py | 2026-05-13 — Fixed silent observation-loss bug: when `report_payload` is present, REQUIRE `GATEWAY_SERVICE_URL` (+ PAT, grant_token, patient_guid). Missing any → loud ERROR log + keep data local. No more silent fallback to request.pdhc (which 200 OKs but discards observations). Status-only path now passes `path='/provider/status'` (canonical on request.pdhc). |
| provider_portal/app/services/upstream_client.py | 2026-05-13 — `submit_report()` gained optional `path` parameter (default `/provider/report`). Used to direct status-only calls to request.pdhc's canonical `/provider/status` path. |
| provider_portal/tests/test_status_callback.py | 2026-05-13 — NEW. 4 tests covering: (1) missing GATEWAY_SERVICE_URL with payload → no upstream push + ERROR log, (2) full config → push goes to gateway not request, (3) status-only routes to request.pdhc, (4) missing grant_token blocks the push. Tests pass when isolated; bundled-run fails on pre-existing `keyauth_users` table-redef issue. |
- provider.pdhc/docs/provider_technical_guide.md (Port Allocation section)
