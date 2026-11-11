from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

BOOK_STATUSES = ('Disponible', 'Agotado', 'Inactivo')
MEMBER_STATUSES = ('Activo', 'Inactivo')
USER_ROLES = ('Administrador', 'Bibliotecario')


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='Bibliotecario')
    active = db.Column('is_active', db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def is_active(self):
        return bool(self.active)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def initials(self):
        parts = [part for part in (self.name or '').split() if part]
        if not parts:
            return 'US'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    books = db.relationship('Book', backref='category', lazy=True)


class Book(db.Model):
    __tablename__ = 'books'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    author = db.Column(db.String(160), nullable=False)
    isbn = db.Column(db.String(30), unique=True, nullable=True)
    editorial = db.Column(db.String(120), nullable=True)
    publication_year = db.Column(db.Integer, nullable=True)
    pages = db.Column(db.Integer, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    location = db.Column(db.String(80), nullable=True)
    description = db.Column(db.Text, nullable=True)
    total_copies = db.Column(db.Integer, nullable=False, default=1)
    available_copies = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default='Disponible')
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    loans = db.relationship('Loan', backref='book', lazy=True)

    @property
    def borrowed_copies(self):
        return max(self.total_copies - self.available_copies, 0)

    @property
    def display_status(self):
        if self.status == 'Inactivo':
            return 'Inactivo'
        if self.status == 'Agotado':
            return 'Agotado'
        if self.available_copies <= 0:
            return 'Sin ejemplares'
        return 'Disponible'

    def can_loan(self):
        return self.available_copies > 0 and self.status == 'Disponible'


class Member(db.Model):
    __tablename__ = 'members'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Activo')
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    loans = db.relationship('Loan', backref='member', lazy=True)

    def full_name(self):
        return f'{self.last_name}, {self.first_name}'

    def active_loan_count(self):
        return sum(1 for loan in self.loans if loan.status == 'Prestado')


class Loan(db.Model):
    __tablename__ = 'loans'
    __table_args__ = (
        db.Index('ix_loans_status_due', 'status', 'due_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    loan_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Prestado')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def is_overdue(self):
        if self.status != 'Prestado' or not self.due_date:
            return False
        from app.utils import school_today
        return self.due_date < school_today()

    def days_overdue(self):
        if not self.is_overdue():
            return 0
        from app.utils import school_today
        return (school_today() - self.due_date).days
