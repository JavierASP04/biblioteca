import re
from datetime import timedelta

import pytest

from app import create_app, db
from app.models import Book, Loan, Member, User
from app.utils import school_today


def book_form(**extra):
    data = {
        'title': 'El principito',
        'author': 'Antoine de Saint-Exupéry',
        'isbn': '978-0156012195',
        'editorial': 'Emecé',
        'publication_year': '1943',
        'pages': '96',
        'category_id': '',
        'location': 'Estante A',
        'description': 'Un clásico',
        'total_copies': '2',
        'status': 'Disponible',
    }
    data.update(extra)
    return data


def member_form(**extra):
    data = {
        'first_name': 'Ana',
        'last_name': 'Pérez',
        'cedula': 'V-12345678',
        'phone': '04121234567',
        'email': 'ana@escuela.local',
        'address': 'Barrio Central',
        'status': 'Activo',
    }
    data.update(extra)
    return data


def test_health_and_unknown_page(client):
    health = client.get('/health')
    assert health.status_code == 200
    assert health.get_json()['status'] == 'ok'

    missing = client.get('/no-existe')
    assert missing.status_code == 404
    assert 'Página no encontrada' in missing.get_data(as_text=True)

    assert client.get('/logout').status_code == 405
    assert client.get('/dashboard', follow_redirects=False).status_code == 302


def test_login_and_open_redirect(client):
    bad = client.post('/login', data={'email': 'admin@escuela.local', 'password': 'nope'})
    assert 'incorrectos' in bad.get_data(as_text=True)

    stolen = client.post(
        '/login?next=https://evil.test/phish',
        data={'email': 'admin@escuela.local', 'password': 'admin123'},
        follow_redirects=False,
    )
    assert stolen.status_code == 302
    assert 'evil.test' not in stolen.headers['Location']
    assert stolen.headers['Location'].endswith('/dashboard')

    client.post('/logout')
    safe = client.post(
        '/login?next=/books/',
        data={'email': 'admin@escuela.local', 'password': 'admin123'},
        follow_redirects=False,
    )
    assert safe.headers['Location'].endswith('/books/')


def test_catalog_loans_and_reports(app, logged):
    created = logged.post('/books/create', data=book_form(), follow_redirects=True)
    assert created.status_code == 200
    assert 'El principito' in created.get_data(as_text=True)

    duplicate = logged.post('/books/create', data=book_form(title='Otro'), follow_redirects=True)
    assert 'ISBN' in duplicate.get_data(as_text=True)

    logged.post('/members/create', data=member_form(), follow_redirects=True)
    repeated = logged.post('/members/create', data=member_form(first_name='Luis'), follow_redirects=True)
    assert 'cédula' in repeated.get_data(as_text=True).lower()
    logged.post('/members/create', data=member_form(
        first_name='Luis', last_name='Gómez', cedula='v-87654321', email='luis@escuela.local'
    ), follow_redirects=True)

    with app.app_context():
        book = Book.query.filter_by(title='El principito').one()
        ana = Member.query.filter_by(cedula='V-12345678').one()
        luis = Member.query.filter_by(cedula='V-87654321').one()
        today = school_today()
        book_id = book.id
        ana_id = ana.id
        luis_id = luis.id

    logged.post('/books/categories', data={'name': 'Poesía', 'description': 'Verso'}, follow_redirects=True)
    with app.app_context():
        from app.models import Category
        poetry = Category.query.filter_by(name='Poesía').one()
        poetry_id = poetry.id
    renamed = logged.post(f'/books/categories/{poetry_id}/edit', data={'name': 'Poesía venezolana', 'description': 'Verso'}, follow_redirects=True)
    assert 'actualizada' in renamed.get_data(as_text=True)

    first = logged.post('/loans/create', data={
        'book_id': book_id,
        'member_id': ana_id,
        'loan_date': today.isoformat(),
        'days': '7',
    }, follow_redirects=True)
    assert 'registrado' in first.get_data(as_text=True)
    with app.app_context():
        stored = db.session.get(Book, book_id)
        assert stored.available_copies == 1
        assert stored.total_copies == 2

    logged.post('/loans/create', data={
        'book_id': book_id,
        'member_id': luis_id,
        'loan_date': today.isoformat(),
        'days': '7',
    }, follow_redirects=True)
    with app.app_context():
        stored = db.session.get(Book, book_id)
        assert stored.available_copies == 0
        assert stored.display_status == 'Sin ejemplares'

    sold_out = logged.post('/loans/create', data={
        'book_id': book_id,
        'member_id': ana_id,
        'loan_date': today.isoformat(),
        'days': '7',
    }, follow_redirects=True)
    assert 'no tiene ejemplares' in sold_out.get_data(as_text=True)

    blocked = logged.post(f'/books/edit/{book_id}', data=book_form(total_copies='1'), follow_redirects=True)
    assert 'prestados' in blocked.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Book, book_id).total_copies == 2

    logged.post(f'/books/edit/{book_id}', data=book_form(total_copies='4'), follow_redirects=True)
    with app.app_context():
        stored = db.session.get(Book, book_id)
        assert stored.total_copies == 4
        assert stored.available_copies == 2
        loan = Loan.query.filter_by(book_id=book_id, member_id=ana_id, status='Prestado').one()
        loan_id = loan.id

    logged.post(f'/loans/renew/{loan_id}', data={'days': '7'}, follow_redirects=True)
    with app.app_context():
        loan = db.session.get(Loan, loan_id)
        assert loan.due_date == today + timedelta(days=14)
        assert 'Renovado' in loan.notes

    cannot_delete = logged.post(f'/books/delete/{book_id}', follow_redirects=True)
    assert 'préstamos asociados' in cannot_delete.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Book, book_id) is not None

    logged.post(f'/loans/return/{loan_id}', follow_redirects=True)
    with app.app_context():
        stored = db.session.get(Book, book_id)
        loan = db.session.get(Loan, loan_id)
        assert loan.status == 'Devuelto'
        assert stored.available_copies == 3

    overdue_book = logged.post('/books/create', data=book_form(
        title='Doña Bárbara', author='Rómulo Gallegos', isbn='978-1111111111', total_copies='1'
    ), follow_redirects=True)
    assert overdue_book.status_code == 200
    with app.app_context():
        extra = Book.query.filter_by(title='Doña Bárbara').one()
        extra_id = extra.id
        old = (school_today() - timedelta(days=30)).isoformat()

    logged.post('/loans/create', data={
        'book_id': extra_id,
        'member_id': luis_id,
        'loan_date': old,
        'days': '1',
    }, follow_redirects=True)

    third = logged.post('/books/create', data=book_form(
        title='Canaima', author='Rómulo Gallegos', isbn='978-2222222222', total_copies='1'
    ), follow_redirects=True)
    assert third.status_code == 200
    with app.app_context():
        canaima = Book.query.filter_by(title='Canaima').one()
        canaima_id = canaima.id

    denied = logged.post('/loans/create', data={
        'book_id': canaima_id,
        'member_id': luis_id,
        'loan_date': today.isoformat(),
        'days': '5',
    }, follow_redirects=True)
    assert 'vencido' in denied.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.get(Book, canaima_id).available_copies == 1

    allowed = logged.post('/loans/create', data={
        'book_id': canaima_id,
        'member_id': luis_id,
        'loan_date': today.isoformat(),
        'days': '5',
        'allow_overdue': '1',
    }, follow_redirects=True)
    assert 'registrado' in allowed.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Book, canaima_id).available_copies == 0

    found = logged.get('/buscar?q=principito')
    assert 'El principito' in found.get_data(as_text=True)
    overdue_page = logged.get('/loans/?status=Vencido')
    assert 'Doña Bárbara' in overdue_page.get_data(as_text=True)

    report = logged.get('/reportes/')
    assert report.status_code == 200
    assert 'Poesía venezolana' in report.get_data(as_text=True)
    exported = logged.get('/reportes/libros.csv')
    assert exported.status_code == 200
    assert 'text/csv' in exported.content_type
    assert 'El principito' in exported.get_data(as_text=True)
    assert 'Doña Bárbara' in logged.get('/reportes/prestamos.csv?estado=vencidos').get_data(as_text=True)
    assert 'Ana' in logged.get('/reportes/miembros.csv').get_data(as_text=True)

    assert logged.get('/books/').status_code == 200
    assert logged.get('/members/').status_code == 200
    assert logged.get('/loans/').status_code == 200
    panel = logged.get('/dashboard')
    assert 'Bienvenido' in panel.get_data(as_text=True)


def test_users_account_and_permissions(app, client, logged):
    created = logged.post('/usuarios/crear', data={
        'name': 'Ana Bibliotecaria',
        'email': 'ana.biblio@escuela.local',
        'role': 'Bibliotecario',
        'password': 'biblioteca1',
        'confirm_password': 'biblioteca1',
        'is_active': '1',
    }, follow_redirects=True)
    assert 'creado' in created.get_data(as_text=True)

    with app.app_context():
        user = User.query.filter_by(email='ana.biblio@escuela.local').one()
        assert len(user.password_hash) <= 255
        user_id = user.id
        admin = User.query.filter_by(email='admin@escuela.local').one()
        admin_id = admin.id

    blocked = logged.post(f'/usuarios/{admin_id}/editar', data={
        'name': 'Administrador',
        'email': 'admin@escuela.local',
        'role': 'Administrador',
    }, follow_redirects=True)
    assert 'administrador' in blocked.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.get(User, admin_id).is_active

    client.post('/logout', follow_redirects=True)
    librarian = client.post('/login', data={
        'email': 'ana.biblio@escuela.local',
        'password': 'biblioteca1',
    }, follow_redirects=True)
    assert 'Bienvenido' in librarian.get_data(as_text=True)
    forbidden = client.get('/usuarios/', follow_redirects=True)
    assert 'administrador' in forbidden.get_data(as_text=True).lower()

    client.post('/logout', follow_redirects=True)
    client.post('/login', data={'email': 'admin@escuela.local', 'password': 'admin123'}, follow_redirects=True)
    client.post(f'/usuarios/{user_id}/editar', data={
        'name': 'Ana Bibliotecaria',
        'email': 'ana.biblio@escuela.local',
        'role': 'Bibliotecario',
    }, follow_redirects=True)
    client.post('/logout', follow_redirects=True)
    rejected = client.post('/login', data={
        'email': 'ana.biblio@escuela.local',
        'password': 'biblioteca1',
    }, follow_redirects=True)
    assert 'desactivada' in rejected.get_data(as_text=True)

    client.post('/login', data={'email': 'admin@escuela.local', 'password': 'admin123'}, follow_redirects=True)
    changed = client.post('/cuenta', data={
        'name': 'Administrador general',
        'current_password': 'admin123',
        'new_password': 'nueva-clave-1',
        'confirm_password': 'nueva-clave-1',
    }, follow_redirects=True)
    assert 'actualizados' in changed.get_data(as_text=True)
    client.post('/logout', follow_redirects=True)
    old = client.post('/login', data={'email': 'admin@escuela.local', 'password': 'admin123'})
    assert 'incorrectos' in old.get_data(as_text=True)
    fresh = client.post('/login', data={'email': 'admin@escuela.local', 'password': 'nueva-clave-1'}, follow_redirects=True)
    assert 'Administrador general' in fresh.get_data(as_text=True)


def test_login_csrf_roundtrip():
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key-csrf',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'PRODUCTION': False,
    })
    client = application.test_client()
    denied = client.post('/login', data={'email': 'admin@escuela.local', 'password': 'admin123'})
    assert denied.status_code == 302
    assert '/login' in denied.headers['Location']

    page = client.get('/login')
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    assert token
    ok = client.post('/login', data={
        'email': 'admin@escuela.local',
        'password': 'admin123',
        'csrf_token': token.group(1),
    }, follow_redirects=True)
    assert 'Panel de Control' in ok.get_data(as_text=True)


def test_production_settings_are_required(monkeypatch):
    monkeypatch.setenv('PRODUCTION', '1')
    monkeypatch.setenv('SECRET_KEY', 'clave-segura-cambiar-en-produccion')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://biblioteca:biblioteca@db:5432/biblioteca')
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()

    monkeypatch.setenv('SECRET_KEY', 'una-clave-larga-de-produccion')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('POSTGRES_URL', raising=False)
    monkeypatch.delenv('MYSQL_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        create_app()
