import os

from dotenv import load_dotenv

PLACEHOLDER_SECRETS = {
    '',
    'clave-segura-cambiar-en-produccion',
    'changeme',
    'change-me',
    'secret',
    'cambiar',
}


def env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_database_url(url):
    if not url:
        return None
    url = url.strip().strip('"').strip("'")
    if url.startswith('postgres://'):
        return 'postgresql+psycopg://' + url[len('postgres://'):]
    if url.startswith('postgresql+psycopg2://'):
        return 'postgresql+psycopg://' + url[len('postgresql+psycopg2://'):]
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg://' + url[len('postgresql://'):]
    if url.startswith('mysql://'):
        return 'mysql+pymysql://' + url[len('mysql://'):]
    return url


def database_url_from_env():
    raw = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('POSTGRES_URL')
        or os.environ.get('MYSQL_URL')
    )
    return normalize_database_url(raw)


def load_settings(config_override=None):
    config_override = dict(config_override or {})
    if not config_override.get('TESTING'):
        load_dotenv()

    testing = bool(config_override.get('TESTING')) or env_flag('TESTING')
    production = env_flag('PRODUCTION')
    if 'PRODUCTION' in config_override:
        production = bool(config_override['PRODUCTION'])

    secret = config_override.get('SECRET_KEY') or os.environ.get('SECRET_KEY') or ''
    secret = secret.strip()
    if production and not testing:
        if secret in PLACEHOLDER_SECRETS or len(secret) < 16:
            raise RuntimeError(
                'En producción defina SECRET_KEY con un valor aleatorio de al menos 16 caracteres. '
                'No use la clave de ejemplo.'
            )

    if config_override.get('SQLALCHEMY_DATABASE_URI'):
        database_url = normalize_database_url(config_override['SQLALCHEMY_DATABASE_URI'])
    else:
        database_url = database_url_from_env() or 'sqlite:///biblioteca.db'

    if production and not testing and database_url.startswith('sqlite'):
        raise RuntimeError(
            'En producción defina DATABASE_URL con la URL interna de PostgreSQL o MySQL. '
            'SQLite no conserva los datos al redesplegar en Coolify.'
        )

    if not secret:
        secret = 'dev-secret-no-usar-en-produccion'

    behind_proxy = production or env_flag('TRUST_PROXY')
    admin_email = (os.environ.get('ADMIN_EMAIL') or 'admin@escuela.local').strip().lower()
    if testing:
        demo_password = 'admin123'
        demo_email = 'admin@escuela.local'
    elif not production:
        demo_password = os.environ.get('ADMIN_PASSWORD') or 'admin123'
        demo_email = admin_email
    else:
        demo_password = None
        demo_email = admin_email

    settings = {
        'SECRET_KEY': secret,
        'PRODUCTION': production,
        'TESTING': testing,
        'SQLALCHEMY_DATABASE_URI': database_url,
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SCHOOL_TZ': os.environ.get('TZ') or os.environ.get('SCHOOL_TZ') or 'America/Caracas',
        'BEHIND_PROXY': behind_proxy,
        'SHOW_DEMO_HINT': bool(demo_password) and not production,
        'DEMO_EMAIL': demo_email,
        'DEMO_PASSWORD': demo_password,
        'ADMIN_EMAIL': demo_email if testing else admin_email,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SAMESITE': 'Lax',
        'SESSION_COOKIE_SECURE': production,
        'REMEMBER_COOKIE_HTTPONLY': True,
        'REMEMBER_COOKIE_SAMESITE': 'Lax',
        'REMEMBER_COOKIE_SECURE': production,
        'WTF_CSRF_TIME_LIMIT': 60 * 60 * 8,
        'WTF_CSRF_SSL_STRICT': not behind_proxy,
        'MAX_CONTENT_LENGTH': 1024 * 1024,
        'SEND_FILE_MAX_AGE_DEFAULT': 3600 if production else 0,
        'PREFERRED_URL_SCHEME': 'https' if production else 'http',
    }
    return settings
