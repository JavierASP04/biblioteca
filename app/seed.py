import os
import secrets

from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Book, Category, User

DEFAULT_CATEGORIES = (
    ('Literatura', 'Novelas, cuentos, poesía y obras literarias.'),
    ('Ciencia y Tecnología', 'Libros de ciencias, tecnología y computación.'),
    ('Historia', 'Obras sobre historia universal y de Venezuela.'),
    ('Matemáticas', 'Textos y guías de matemáticas.'),
    ('Educación', 'Materiales didácticos y pedagógicos.'),
    ('Referencia', 'Diccionarios, enciclopedias y obras de consulta.'),
    ('Infantil', 'Cuentos y material para niños.'),
)


def seed_database(app):
    if app.config.get('TESTING'):
        email = 'admin@escuela.local'
        password = 'admin123'
        name = 'Administrador'
        generated = False
    else:
        email = (os.environ.get('ADMIN_EMAIL') or 'admin@escuela.local').strip().lower()
        name = (os.environ.get('ADMIN_NAME') or 'Administrador').strip() or 'Administrador'
        password = os.environ.get('ADMIN_PASSWORD')
        generated = False
        if not password:
            if app.config.get('PRODUCTION'):
                password = secrets.token_urlsafe(12)
                generated = True
            else:
                password = 'admin123'

    if User.query.count() == 0:
        admin = User(name=name[:100], email=email[:120], role='Administrador', active=True)
        admin.set_password(password)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            if generated:
                app.logger.warning(
                    'No se definió ADMIN_PASSWORD. Usuario %s creado con contraseña temporal: %s',
                    email,
                    password,
                )
            elif app.config.get('PRODUCTION') and password == 'admin123':
                app.logger.warning(
                    'El administrador %s usa la contraseña de demostración admin123. Cámbiela en Mi cuenta.',
                    email,
                )

    if app.config.get('PRODUCTION') and not app.config.get('TESTING'):
        for admin in User.query.filter_by(role='Administrador', active=True).all():
            if admin.check_password('admin123'):
                app.logger.warning(
                    'La cuenta %s sigue usando la contraseña admin123. Cámbiela desde Mi cuenta.',
                    admin.email,
                )
                break

    if Category.query.count() == 0 and Book.query.count() == 0:
        for category_name, description in DEFAULT_CATEGORIES:
            db.session.add(Category(name=category_name, description=description))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
