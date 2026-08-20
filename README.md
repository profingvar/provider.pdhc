# provider.pdhc

Provider portal service for the **PDHC** platform.

This is one of the service repositories that together form
[Planned Data in Healthcare](https://pdhc.se). It is the
external-provider side of the request/response loop: it receives
care-plan-driven `ServiceRequest` payloads pushed from `request.pdhc`,
makes them available to a clinical provider (e.g. a remote-monitoring
or follow-up clinic), and submits the resulting observations and
reports back through `gateway.pdhc`.

The reference deployment of this codebase is the **Provider1** portal
(`provider1.pdhc.se`) — a demo external provider running asthma / COPD
remote follow-up. Note: "Provider1" is this reference portal's own
identity and is deliberately distinct from the real external partner
**Medituner AB** (SSO org `7a69ab02…`), which runs its own receiver
rather than this portal.

## What this service does

- Receives `ServiceRequest` payloads pushed from `request.pdhc` with
  HMAC-signed grant tokens
- Surfaces them in a Flask portal for clinician/provider workflows
- Submits the resulting `Observation` and report bundles back to
  `gateway.pdhc`
- Tracks delivery receipts, audit logs, and care-plan caches
- One provider per instance (`PROVIDER_GUID` / `PROVIDER_NAME` set in
  `.env`)

## Layout

- `provider_portal/` — Flask application, models, services, API endpoints, migrations
- `docs/` — technical guide, user guide, design references
- `start.sh` — single entry point
- `provider_portal/.env.example` — required environment variables
- `DEPLOYMENT_PLAN.md` — historical phased deployment plan (internal reference)

## Running locally

```bash
cd provider_portal
cp .env.example .env       # then fill in the values
docker compose up -d db    # postgres on 9071
flask db upgrade
python -m gunicorn --bind 127.0.0.1:9070 'app:create_app()'
```

See `docs/provider_technical_guide.md` for the full integration model
and `provider_portal/.env.example` for required environment.

## License

MIT — see [LICENSE](LICENSE).
