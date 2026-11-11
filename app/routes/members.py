from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import MEMBER_STATUSES, Loan, Member
from app.utils import get_or_404, optional_email, paginate, text_field

members_bp = Blueprint('members', __name__, url_prefix='/members')


def _member_payload():
    first_name, error = text_field(
        request.form, 'first_name', 80, required=True,
        missing='Los nombres son obligatorios.',
        too_long='Los nombres no pueden superar 80 caracteres.',
    )
    if error:
        return None, error
    last_name, error = text_field(
        request.form, 'last_name', 80, required=True,
        missing='Los apellidos son obligatorios.',
        too_long='Los apellidos no pueden superar 80 caracteres.',
    )
    if error:
        return None, error
    cedula, error = text_field(
        request.form, 'cedula', 20, required=True,
        missing='La cédula es obligatoria.',
        too_long='La cédula no puede superar 20 caracteres.',
    )
    if error:
        return None, error
    phone, error = text_field(
        request.form, 'phone', 20,
        too_long='El teléfono no puede superar 20 caracteres.',
    )
    if error:
        return None, error
    address, error = text_field(
        request.form, 'address', 500,
        too_long='La dirección no puede superar 500 caracteres.',
    )
    if error:
        return None, error
    email, error = optional_email(request.form)
    if error:
        return None, error
    status = request.form.get('status', 'Activo')
    if status not in MEMBER_STATUSES:
        status = 'Activo'
    return {
        'first_name': first_name,
        'last_name': last_name,
        'cedula': cedula.upper(),
        'phone': phone,
        'email': email,
        'address': address,
        'status': status,
    }, None


def _cedula_taken(cedula, member_id=None):
    query = Member.query.filter(db.func.lower(Member.cedula) == cedula.lower())
    if member_id:
        query = query.filter(Member.id != member_id)
    return query.first() is not None


@members_bp.route('/')
@login_required
def list_members():
    query = Member.query
    status = request.args.get('status')
    search = (request.args.get('search') or '').strip()
    if status in MEMBER_STATUSES:
        query = query.filter_by(status=status)
    if search:
        term = f'%{search}%'
        query = query.filter(
            Member.first_name.ilike(term)
            | Member.last_name.ilike(term)
            | Member.cedula.ilike(term)
        )
    pagination = paginate(query.order_by(Member.last_name, Member.first_name))
    stats = {
        'total': Member.query.count(),
        'active': Member.query.filter_by(status='Activo').count(),
        'inactive': Member.query.filter_by(status='Inactivo').count(),
        'with_loans': Member.query.filter(Member.loans.any(Loan.status == 'Prestado')).count(),
    }
    return render_template('members/list.html', members=pagination.items, pagination=pagination, stats=stats)


@members_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_member():
    if request.method == 'POST':
        payload, error = _member_payload()
        if error:
            flash(error, 'error')
        elif _cedula_taken(payload['cedula']):
            flash('Ya existe un miembro con esa cédula.', 'error')
        else:
            member = Member(**payload)
            db.session.add(member)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo registrar el miembro. Revise que la cédula no esté repetida.', 'error')
            else:
                flash(f'Miembro {member.full_name()} registrado.', 'success')
                return redirect(url_for('members.detail', id=member.id))
    return render_template('members/form.html', member=None)


@members_bp.route('/<int:id>')
@login_required
def detail(id):
    member = get_or_404(Member, id)
    loans = sorted(member.loans, key=lambda loan: loan.created_at or loan.loan_date, reverse=True)
    return render_template('members/detail.html', member=member, loans=loans)


@members_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_member(id):
    member = get_or_404(Member, id)
    if request.method == 'POST':
        payload, error = _member_payload()
        if error:
            flash(error, 'error')
        elif _cedula_taken(payload['cedula'], member.id):
            flash('Ya existe un miembro con esa cédula.', 'error')
        else:
            for key, value in payload.items():
                setattr(member, key, value)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo actualizar el miembro.', 'error')
            else:
                flash(f'Datos de {member.full_name()} actualizados.', 'success')
                return redirect(url_for('members.detail', id=member.id))
    return render_template('members/form.html', member=member)


@members_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_member(id):
    member = get_or_404(Member, id)
    if member.loans:
        flash('No se puede eliminar el miembro porque tiene préstamos asociados.', 'error')
        return redirect(url_for('members.detail', id=member.id))
    name = member.full_name()
    db.session.delete(member)
    db.session.commit()
    flash(f'Miembro {name} eliminado.', 'success')
    return redirect(url_for('members.list_members'))
