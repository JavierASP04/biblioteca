from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Book, Loan, Member
from app.utils import get_or_404, int_field, paginate, school_today, text_field

loans_bp = Blueprint('loans', __name__, url_prefix='/loans')


def _same_site(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc and parsed.netloc != request.host:
        return None
    return target


def _back_to_list():
    return redirect(_same_site(request.referrer) or url_for('loans.list_loans'))


def _lock_book(book_id):
    if not book_id:
        return None
    return db.session.query(Book).filter_by(id=book_id).with_for_update().one_or_none()


def _loan_block_reason(book, member, allow_overdue):
    if not book or not member:
        return 'Debe seleccionar un libro y un miembro.'
    if member.status != 'Activo':
        return f'El miembro {member.full_name()} está inactivo.'
    if book.status != 'Disponible':
        return f'El libro "{book.title}" no está disponible para préstamo ({book.status}).'
    if book.available_copies <= 0:
        return f'El libro "{book.title}" no tiene ejemplares disponibles.'
    overdue = Loan.query.filter(
        Loan.member_id == member.id,
        Loan.status == 'Prestado',
        Loan.due_date < school_today(),
    ).count()
    if overdue and not allow_overdue:
        return (
            f'{member.full_name()} tiene {overdue} préstamo(s) vencido(s). '
            'Marque la autorización para continuar.'
        )
    return None


@loans_bp.route('/')
@login_required
def list_loans():
    query = Loan.query
    status = request.args.get('status')
    search = (request.args.get('search') or '').strip()
    today = school_today()

    if status == 'Vencido':
        query = query.filter(Loan.status == 'Prestado', Loan.due_date < today)
    elif status in ('Prestado', 'Devuelto'):
        query = query.filter_by(status=status)
    if search:
        term = f'%{search}%'
        query = (
            query.join(Book, Loan.book_id == Book.id)
            .join(Member, Loan.member_id == Member.id)
            .filter(or_(
                Book.title.ilike(term),
                Book.author.ilike(term),
                Member.first_name.ilike(term),
                Member.last_name.ilike(term),
                Member.cedula.ilike(term),
            ))
        )

    pagination = paginate(query.order_by(Loan.created_at.desc()))
    active = Loan.query.filter_by(status='Prestado')
    stats = {
        'active': active.count(),
        'returned': Loan.query.filter_by(status='Devuelto').count(),
        'overdue': active.filter(Loan.due_date < today).count(),
        'total': Loan.query.count(),
    }
    return render_template(
        'loans/list.html',
        loans=pagination.items,
        pagination=pagination,
        stats=stats,
        today=today,
    )


@loans_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_loan():
    if request.method == 'POST':
        book_id, error = int_field(request.form, 'book_id', required=True, minimum=1, missing='Debe seleccionar un libro.')
        member_id, member_error = int_field(
            request.form, 'member_id', required=True, minimum=1, missing='Debe seleccionar un miembro.'
        )
        if error or member_error:
            flash(error or member_error, 'error')
        else:
            raw_date = (request.form.get('loan_date') or '').strip()
            try:
                loan_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                flash('La fecha de préstamo no es válida.', 'error')
                return _loan_form()
            if loan_date.year < 2000 or loan_date > school_today():
                flash('La fecha de préstamo no puede ser futura ni anterior al año 2000.', 'error')
                return _loan_form()
            days, error = int_field(
                request.form, 'days', required=True, minimum=1, maximum=90,
                missing='Indique el plazo en días.',
                out_of_range='El plazo debe estar entre 1 y 90 días.',
            )
            if error:
                flash(error, 'error')
                return _loan_form()
            notes, error = text_field(
                request.form, 'notes', 2000,
                too_long='Las notas no pueden superar 2000 caracteres.',
            )
            if error:
                flash(error, 'error')
                return _loan_form()

            member = db.session.get(Member, member_id)
            book = _lock_book(book_id)
            reason = _loan_block_reason(book, member, request.form.get('allow_overdue') == '1')
            if reason:
                db.session.rollback()
                flash(reason, 'error')
            else:
                loan = Loan(
                    book_id=book.id,
                    member_id=member.id,
                    loan_date=loan_date,
                    due_date=loan_date + timedelta(days=days),
                    notes=notes,
                )
                book.available_copies -= 1
                db.session.add(loan)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('No se pudo registrar el préstamo.', 'error')
                else:
                    flash(
                        f'Préstamo de "{book.title}" registrado para {member.full_name()}. '
                        f'Devolución prevista el {loan.due_date.strftime("%d/%m/%Y")}.',
                        'success',
                    )
                    return redirect(url_for('loans.list_loans'))
    return _loan_form()


def _loan_form():
    books = (
        Book.query.filter(Book.available_copies > 0, Book.status == 'Disponible')
        .order_by(Book.title)
        .all()
    )
    members = Member.query.filter_by(status='Activo').order_by(Member.last_name, Member.first_name).all()
    return render_template(
        'loans/form.html',
        books=books,
        members=members,
        today=school_today().isoformat(),
    )


@loans_bp.route('/return/<int:id>', methods=['POST'])
@login_required
def return_loan(id):
    loan = get_or_404(Loan, id)
    if loan.status != 'Prestado':
        flash('Este préstamo ya fue devuelto.', 'info')
        return redirect(url_for('loans.list_loans'))
    book = _lock_book(loan.book_id)
    loan.return_date = school_today()
    loan.status = 'Devuelto'
    if book and book.available_copies < book.total_copies:
        book.available_copies += 1
    db.session.commit()
    flash(f'Libro "{loan.book.title}" devuelto correctamente.', 'success')
    return _back_to_list()


@loans_bp.route('/renew/<int:id>', methods=['POST'])
@login_required
def renew_loan(id):
    loan = get_or_404(Loan, id)
    if loan.status != 'Prestado':
        flash('Solo se pueden renovar préstamos activos.', 'error')
        return redirect(url_for('loans.list_loans'))
    days, error = int_field(
        request.form, 'days', minimum=1, maximum=30,
        out_of_range='La renovación debe estar entre 1 y 30 días.',
    )
    if error:
        flash(error, 'error')
        return redirect(url_for('loans.list_loans'))
    days = days or 7
    base = loan.due_date if loan.due_date > school_today() else school_today()
    loan.due_date = base + timedelta(days=days)
    stamp = school_today().strftime('%d/%m/%Y')
    extra = f'Renovado el {stamp} (+{days} días).'
    loan.notes = f'{loan.notes}\n{extra}'.strip() if loan.notes else extra
    db.session.commit()
    flash(
        f'Préstamo renovado. Nueva fecha de entrega: {loan.due_date.strftime("%d/%m/%Y")}.',
        'success',
    )
    return _back_to_list()


@loans_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_loan(id):
    loan = get_or_404(Loan, id)
    title = loan.book.title
    if loan.status == 'Prestado':
        book = _lock_book(loan.book_id)
        if book:
            book.available_copies = min(book.available_copies + 1, book.total_copies)
    db.session.delete(loan)
    db.session.commit()
    flash(f'Préstamo de "{title}" eliminado.', 'success')
    return redirect(url_for('loans.list_loans'))
