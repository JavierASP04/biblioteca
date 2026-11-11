from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models import Book, Category, Loan, Member
from app.utils import csv_download, school_today

reports_bp = Blueprint('reports', __name__, url_prefix='/reportes')


def _category_rows():
    rows = (
        db.session.query(
            Category.name,
            func.count(Book.id),
            func.coalesce(func.sum(Book.total_copies), 0),
            func.coalesce(func.sum(Book.available_copies), 0),
        )
        .outerjoin(Book, Book.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(Category.name)
        .all()
    )
    result = [
        {
            'name': name,
            'titles': int(titles or 0),
            'copies': int(copies or 0),
            'available': int(available or 0),
        }
        for name, titles, copies, available in rows
    ]
    uncategorized = Book.query.filter(Book.category_id.is_(None))
    extra_titles = uncategorized.count()
    if extra_titles:
        copies = int(db.session.query(func.coalesce(func.sum(Book.total_copies), 0)).filter(Book.category_id.is_(None)).scalar() or 0)
        available = int(db.session.query(func.coalesce(func.sum(Book.available_copies), 0)).filter(Book.category_id.is_(None)).scalar() or 0)
        result.append({
            'name': 'Sin categoría',
            'titles': extra_titles,
            'copies': copies,
            'available': available,
        })
    return result


@reports_bp.route('/')
@login_required
def index():
    today = school_today()
    active = Loan.query.filter_by(status='Prestado')
    overdue = active.filter(Loan.due_date < today).order_by(Loan.due_date.asc()).all()
    active_loans = active.order_by(Loan.due_date.asc()).limit(40).all()
    ranking = (
        db.session.query(Book.id, func.count(Loan.id).label('total'))
        .join(Loan, Loan.book_id == Book.id)
        .group_by(Book.id)
        .order_by(func.count(Loan.id).desc())
        .limit(5)
        .all()
    )
    top_books = [(db.session.get(Book, book_id), total) for book_id, total in ranking]
    stats = {
        'books': Book.query.count(),
        'copies': int(db.session.query(func.coalesce(func.sum(Book.total_copies), 0)).scalar() or 0),
        'available': int(db.session.query(func.coalesce(func.sum(Book.available_copies), 0)).scalar() or 0),
        'members': Member.query.filter_by(status='Activo').count(),
        'active_loans': active.count(),
        'overdue': len(overdue),
    }
    return render_template(
        'reports/index.html',
        stats=stats,
        categories=_category_rows(),
        overdue_loans=overdue,
        active_loans=active_loans,
        active_total=stats['active_loans'],
        top_books=top_books,
        today=today,
    )


@reports_bp.route('/libros.csv')
@login_required
def books_csv():
    books = Book.query.order_by(Book.title).all()
    rows = [
        [
            book.isbn or '',
            book.title,
            book.author,
            book.category.name if book.category else '',
            book.editorial or '',
            book.publication_year or '',
            book.pages or '',
            book.location or '',
            book.total_copies,
            book.available_copies,
            book.borrowed_copies,
            book.display_status,
        ]
        for book in books
    ]
    return csv_download(
        'inventario-biblioteca.csv',
        ['ISBN', 'Título', 'Autor', 'Categoría', 'Editorial', 'Año', 'Páginas', 'Ubicación',
         'Ejemplares', 'Disponibles', 'Prestados', 'Estado'],
        rows,
    )


@reports_bp.route('/prestamos.csv')
@login_required
def loans_csv():
    estado = request.args.get('estado', 'todos')
    today = school_today()
    query = Loan.query.join(Book, Loan.book_id == Book.id).join(Member, Loan.member_id == Member.id)
    if estado == 'vencidos':
        query = query.filter(Loan.status == 'Prestado', Loan.due_date < today)
        filename = 'prestamos-vencidos.csv'
    elif estado == 'activos':
        query = query.filter(Loan.status == 'Prestado')
        filename = 'prestamos-activos.csv'
    else:
        filename = 'prestamos.csv'
    loans = query.order_by(Loan.loan_date.desc()).all()
    rows = []
    for loan in loans:
        state = 'Vencido' if loan.is_overdue() else loan.status
        rows.append([
            loan.book.title,
            loan.book.author,
            loan.member.full_name(),
            loan.member.cedula,
            loan.member.phone or '',
            loan.loan_date.strftime('%d/%m/%Y'),
            loan.due_date.strftime('%d/%m/%Y'),
            loan.return_date.strftime('%d/%m/%Y') if loan.return_date else '',
            state,
            loan.days_overdue() or '',
            loan.notes or '',
        ])
    return csv_download(
        filename,
        ['Libro', 'Autor', 'Miembro', 'Cédula', 'Teléfono', 'Préstamo', 'Entrega prevista',
         'Devolución', 'Estado', 'Días de retraso', 'Notas'],
        rows,
    )


@reports_bp.route('/miembros.csv')
@login_required
def members_csv():
    members = Member.query.order_by(Member.last_name, Member.first_name).all()
    rows = [
        [
            member.cedula,
            member.last_name,
            member.first_name,
            member.phone or '',
            member.email or '',
            member.address or '',
            member.status,
            member.active_loan_count(),
            len(member.loans),
        ]
        for member in members
    ]
    return csv_download(
        'miembros-biblioteca.csv',
        ['Cédula', 'Apellidos', 'Nombres', 'Teléfono', 'Correo', 'Dirección', 'Estado',
         'Préstamos activos', 'Historial'],
        rows,
    )
