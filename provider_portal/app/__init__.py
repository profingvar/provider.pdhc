from flask import Flask
from .extensions import db, migrate
from config import Config


def create_app(config_class=Config):
    app = Flask(
        __name__,
        static_folder='../static',
        template_folder='../templates',
    )
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from .api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    from .web import web_bp
    app.register_blueprint(web_bp)

    from .errors import register_error_handlers
    register_error_handlers(app)

    from .cli import sync_cli
    app.cli.add_command(sync_cli)

    # Key-based user authentication
    app.config.setdefault('KEYAUTH_PORTAL_NAME', 'Provider Portal')
    app.config.setdefault('KEYAUTH_DASHBOARD_ENDPOINT', 'web.dashboard')
    app.config.setdefault('KEYAUTH_BOOTSTRAP_USER', 'admin')
    if app.config.get('BOOTSTRAP_API_KEY'):
        app.config.setdefault('KEYAUTH_BOOTSTRAP_KEY', app.config['BOOTSTRAP_API_KEY'])

    from pdhc_keyauth import init_keyauth
    init_keyauth(app, db)

    @app.route('/api/v1/health')
    def health():
        from flask import jsonify
        from sqlalchemy import text
        db_ok = False
        try:
            db.session.execute(text('SELECT 1'))
            db_ok = True
        except Exception:
            pass
        status = 'ok' if db_ok else 'degraded'
        code = 200 if db_ok else 503
        resp = jsonify({
            'status': status,
            'database': 'connected' if db_ok else 'unavailable',
            'service': 'provider1.pdhc',
        })
        # Ticket #70 / CLAUDE.md §10: let www.pdhc.se/services.html read the
        # JSON body cross-origin so it can drive real status/DB dots. Specific
        # origin + Vary: Origin (not "*") keeps future Allow-Credentials
        # spec-compliant.
        resp.headers['Access-Control-Allow-Origin'] = 'https://www.pdhc.se'
        resp.headers['Access-Control-Allow-Methods'] = 'GET'
        resp.headers['Vary'] = 'Origin'
        resp.headers['Cache-Control'] = 'no-store'
        return resp, code

    with app.app_context():
        _bootstrap_admin(app)
        _reconcile_provider_guid(app)

    # Start background sync if enabled (not in testing)
    if app.config.get('SYNC_ENABLED') and not app.config.get('TESTING'):
        _start_background_sync(app)

    _register_stockholm_filter(app)

    return app


def _start_background_sync(app):
    from .services.subscription import RequestSubscriptionService
    from .services.sync_scheduler import SyncScheduler

    svc = RequestSubscriptionService(app=app)
    scheduler = SyncScheduler(app=app, subscription_service=svc)
    scheduler.start()
    app.extensions['sync_scheduler'] = scheduler


def _bootstrap_admin(app):
    """Create bootstrap provider + API key on first run if table exists."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if not inspector.has_table('providers'):
        return

    from .models import Provider, ApiKey
    bootstrap_key = app.config.get('BOOTSTRAP_API_KEY')
    if not bootstrap_key:
        return

    existing = Provider.query.filter_by(name=app.config['BOOTSTRAP_PROVIDER_NAME']).first()
    if existing:
        return

    import uuid
    provider = Provider(
        guid=app.config.get('PROVIDER_GUID') or str(uuid.uuid4()),
        name=app.config['BOOTSTRAP_PROVIDER_NAME'],
        is_active=True,
    )
    db.session.add(provider)
    db.session.flush()

    api_key = ApiKey.create(
        provider_guid=provider.guid,
        raw_key=bootstrap_key,
        scopes='read,write',
        label='bootstrap',
    )
    db.session.add(api_key)
    db.session.commit()

def _reconcile_provider_guid(app):
    """Ticket 7: ensure a providers row exists matching PROVIDER_GUID from
    config so provider_tasks FK never fails after a PROVIDER_GUID rotation."""
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if not inspector.has_table("providers"):
        return
    guid = app.config.get("PROVIDER_GUID")
    if not guid:
        return
    from .models import Provider
    if Provider.query.filter_by(guid=guid).first():
        return
    name = app.config.get("BOOTSTRAP_PROVIDER_NAME") or app.config.get("KEYAUTH_PORTAL_NAME") or "Provider"
    db.session.add(Provider(guid=guid, name=name, is_active=True))
    db.session.commit()
    app.logger.info("reconciled providers row for PROVIDER_GUID=%s", guid)


# ── Ticket 9: Stockholm-local timestamp filter ─────────────────────────
def _register_stockholm_filter(app):
    """Register `local` Jinja filter rendering datetimes as Europe/Stockholm."""
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        return
    from datetime import datetime, timezone
    _STO = ZoneInfo("Europe/Stockholm")

    def _local(value, fmt="%Y-%m-%d %H:%M"):
        if value is None or value == "":
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                return value
        if getattr(value, "tzinfo", None) is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(_STO).strftime(fmt)

    app.jinja_env.filters["local"] = _local
