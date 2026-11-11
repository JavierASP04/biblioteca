import logging
import time
from datetime import timedelta
from urllib.parse import urlparse

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.pool import StaticPool
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import load_settings
from app.utils import safe_next_url, school_today

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_override=None):
    settings = load_settings(config_override)
    app = Flask(__name__)
    app.config.update(settings)
    app.config.update(config_override or {})
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=14)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
    app.json.ensure_ascii = False

    database_url = app.config['SQLALCHEMY_DATABASE_URI']
    if database_url == 'sqlite:///:memory:':
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {'check_same_thread': False},
            'poolclass': StaticPool,
        }
    elif database_url.startswith(('postgresql', 'mysql')):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 280,
            'connect_args': {'connect_timeout': 5},
        }

    if app.config.get('BEHIND_PROXY'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Debe iniciar sesión para continuar.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'basic'

    from app.models import Loan, User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from app.routes.auth import auth_bp
    from app.routes.books import books_bp
    from app.routes.loans import loans_bp
    from app.routes.main import main_bp
    from app.routes.members import members_bp
    from app.routes.reports import reports_bp
    from app.routes.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)

    @app.context_processor
    def inject_layout():
        overdue_count = 0
        try:
            if getattr(current_user, 'is_authenticated', False):
                overdue_count = Loan.query.filter(
                    Loan.status == 'Prestado',
                    Loan.due_date < school_today(),
                ).count()
        except Exception:
            app.logger.exception('No se pudo calcular el conteo de vencidos')
            overdue_count = 0
        return {
            'overdue_count': overdue_count,
            'show_demo_hint': app.config.get('SHOW_DEMO_HINT', False),
            'demo_email': app.config.get('DEMO_EMAIL'),
            'demo_password': app.config.get('DEMO_PASSWORD'),
        }

    @app.before_request
    def block_disabled_accounts():
        if request.endpoint in {'health', 'static', 'auth.login', 'auth.logout'}:
            return None
        user_id = current_user.get_id() if hasattr(current_user, 'get_id') else None
        if user_id and hasattr(current_user, 'check_password') and not current_user.is_active:
            logout_user()
            flash('Su cuenta fue desactivada. Contacte al administrador.', 'error')
            return redirect(url_for('auth.login'))
        return None

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.get('/health')
    def health():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify(status='ok')
        except Exception:
            app.logger.exception('Fallo el chequeo de salud')
            return jsonify(status='error'), 503

    @app.errorhandler(CSRFError)
    def handle_csrf(error):
        app.logger.info('CSRF rechazado: %s', error.description)
        flash('El formulario expiró o no es válido. Vuelva a intentarlo.', 'error')
        referrer = request.referrer or ''
        if referrer and urlparse(referrer).netloc == request.host:
            return redirect(referrer)
        if getattr(current_user, 'is_authenticated', False):
            return redirect(url_for('main.dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            'errors/error.html',
            code=404,
            title='Página no encontrada',
            message='La dirección no existe o fue movida.',
        ), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template(
            'errors/error.html',
            code=413,
            title='Solicitud demasiado grande',
            message='Los datos enviados superan el tamaño permitido.',
        ), 413

    @app.errorhandler(Exception)
    def unhandled(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception('Error no controlado')
        db.session.rollback()
        return render_template(
            'errors/error.html',
            code=500,
            title='Error interno',
            message='Ocurrió un problema inesperado. Intente de nuevo en unos minutos.',
        ), 500

    with app.app_context():
        _init_database(app)

    return app


def _init_database(app):
    from app.seed import seed_database

    attempts = 1 if app.config.get('TESTING') or not app.config.get('PRODUCTION') else 10
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            db.create_all()
            seed_database(app)
            return
        except (OperationalError, InterfaceError) as exc:
            last_error = exc
            db.session.rollback()
            db.engine.dispose()
            app.logger.warning(
                'Base de datos no disponible (intento %s/%s): %s',
                attempt,
                attempts,
                exc,
            )
            if attempt == attempts:
                break
            time.sleep(2)
    raise RuntimeError(
        'No se pudo conectar a la base de datos. Revise DATABASE_URL y que el servicio esté en marcha.'
    ) from last_error
