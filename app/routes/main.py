from flask import Blueprint, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.models import Book, Category, Loan, Member
from app.utils import clean, school_today

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    modules = [
        {
            'name': 'Inventario de Libros',
            'description': 'Registro y control del catálogo de libros de la biblioteca.',
            'icon': 'fa-book',
            'color': '#4A90D9',
            'route': url_for('books.list_books'),
        },
        {
            'name': 'Préstamos',
            'description': 'Registro de préstamos, devoluciones y control de plazos.',
            'icon': 'fa-hand-holding',
            'color': '#27AE60',
            'route': url_for('loans.list_loans'),
        },
        {
            'name': 'Miembros y Lectores',
            'description': 'Administración de los usuarios registrados en la biblioteca.',
            'icon': 'fa-user-friends',
            'color': '#F39C12',
            'route': url_for('members.list_members'),
        },
        {
            'name': 'Categorías',
            'description': 'Clasificación de los libros por género y temática.',
            'icon': 'fa-tags',
            'color': '#E74C3C',
            'route': url_for('books.list_categories'),
        },
        {
            'name': 'Reportes',
            'description': 'Inventario, préstamos vencidos y exportación para Excel.',
            'icon': 'fa-chart-bar',
            'color': '#8E44AD',
            'route': url_for('reports.index'),
        },
    ]
    if current_user.role == 'Administrador':
        modules.append({
            'name': 'Usuarios del sistema',
            'description': 'Cuentas del personal que administra la biblioteca.',
            'icon': 'fa-user-shield',
            'color': '#16A085',
            'route': url_for('users.list_users'),
        })

    today = school_today()
    active_loans = Loan.query.filter_by(status='Prestado')
    copies = int(db.session.query(func.coalesce(func.sum(Book.total_copies), 0)).scalar() or 0)
    available = int(db.session.query(func.coalesce(func.sum(Book.available_copies), 0)).scalar() or 0)
    stats = {
        'books': Book.query.count(),
        'copies': copies,
        'available': available,
        'members': Member.query.count(),
        'active_loans': active_loans.count(),
        'overdue': active_loans.filter(Loan.due_date < today).count(),
        'categories': Category.query.count(),
    }
    overdue_loans = (
        active_loans.filter(Loan.due_date < today)
        .order_by(Loan.due_date.asc())
        .limit(8)
        .all()
    )
    recent_loans = Loan.query.order_by(Loan.created_at.desc()).limit(6).all()
    return render_template(
        'dashboard.html',
        modules=modules,
        stats=stats,
        overdue_loans=overdue_loans,
        recent_loans=recent_loans,
    )


@main_bp.route('/buscar')
@login_required
def search():
    q = clean(request.args.get('q'))
    books = []
    members = []
    loans = []
    too_short = len(q) < 2
    if not too_short:
        term = f'%{q}%'
        books = (
            Book.query.filter(or_(
                Book.title.ilike(term),
                Book.author.ilike(term),
                Book.isbn.ilike(term),
            ))
            .order_by(Book.title)
            .limit(20)
            .all()
        )
        members = (
            Member.query.filter(or_(
                Member.first_name.ilike(term),
                Member.last_name.ilike(term),
                Member.cedula.ilike(term),
            ))
            .order_by(Member.last_name)
            .limit(20)
            .all()
        )
        loans = (
            Loan.query
            .join(Book, Loan.book_id == Book.id)
            .join(Member, Loan.member_id == Member.id)
            .filter(or_(
                Book.title.ilike(term),
                Member.first_name.ilike(term),
                Member.last_name.ilike(term),
                Member.cedula.ilike(term),
            ))
            .order_by(Loan.created_at.desc())
            .limit(20)
            .all()
        )
    return render_template(
        'search.html',
        q=q,
        books=books,
        members=members,
        loans=loans,
        too_short=too_short,
    )
