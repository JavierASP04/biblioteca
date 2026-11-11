import pytest

from app import create_app, db


@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'PRODUCTION': False,
    })
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    def _login(email='admin@escuela.local', password='admin123'):
        return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
    return _login


@pytest.fixture
def logged(client, auth):
    auth()
    return client
