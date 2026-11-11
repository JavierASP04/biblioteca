from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import USER_ROLES, User
from app.utils import admin_required, get_or_404, optional_email, text_field

users_bp = Blueprint('users', __name__, url_prefix='/usuarios')


def _keeps_an_admin(user, role, active):
    if user.role != 'Administrador' or not user.active:
        return True
    if role == 'Administrador' and active:
        return True
    others = User.query.filter(
        User.role == 'Administrador',
        User.active.is_(True),
        User.id != user.id,
    ).count()
    return others > 0


def _user_fields(user=None):
    name, error = text_field(
        request.form, 'name', 100, required=True,
        missing='El nombre es obligatorio.',
        too_long='El nombre no puede superar 100 caracteres.',
    )
    if error:
        return None, error
    email, error = optional_email(request.form)
    if error or not email:
        return None, error or 'El correo electrónico es obligatorio.'
    role = request.form.get('role', 'Bibliotecario')
    if role not in USER_ROLES:
        role = 'Bibliotecario'
    active = request.form.get('is_active') == '1'
    password = request.form.get('password') or ''
    confirm = request.form.get('confirm_password') or ''
    if user is None and len(password) < 8:
        return None, 'La contraseña debe tener al menos 8 caracteres.'
    if password or confirm:
        if len(password) < 8:
            return None, 'La contraseña debe tener al menos 8 caracteres.'
        if password != confirm:
            return None, 'La confirmación de la contraseña no coincide.'
    taken = User.query.filter(db.func.lower(User.email) == email)
    if user:
        taken = taken.filter(User.id != user.id)
    if taken.first():
        return None, 'Ya existe un usuario con ese correo.'
    if user and not _keeps_an_admin(user, role, active):
        return None, 'Debe quedar al menos un administrador activo.'
    return {
        'name': name,
        'email': email,
        'role': role,
        'active': active,
        'password': password,
    }, None


@users_bp.route('/')
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.name).all()
    return render_template('users/list.html', users=users)


@users_bp.route('/crear', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        payload, error = _user_fields()
        if error:
            flash(error, 'error')
        else:
            user = User(
                name=payload['name'],
                email=payload['email'],
                role=payload['role'],
                active=payload['active'],
            )
            user.set_password(payload['password'])
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo crear el usuario. El correo ya está registrado.', 'error')
            else:
                flash(f'Usuario {user.name} creado.', 'success')
                return redirect(url_for('users.list_users'))
    return render_template('users/form.html', user=None)


@users_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = get_or_404(User, id)
    if request.method == 'POST':
        payload, error = _user_fields(user)
        if error:
            flash(error, 'error')
        else:
            user.name = payload['name']
            user.email = payload['email']
            user.role = payload['role']
            user.active = payload['active']
            if payload['password']:
                user.set_password(payload['password'])
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo actualizar el usuario.', 'error')
            else:
                flash(f'Usuario {user.name} actualizado.', 'success')
                return redirect(url_for('users.list_users'))
    return render_template('users/form.html', user=user)


@users_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = get_or_404(User, id)
    if user.id == current_user.id:
        flash('No puede eliminar su propia cuenta.', 'error')
        return redirect(url_for('users.list_users'))
    if not _keeps_an_admin(user, 'Bibliotecario', False):
        flash('No puede eliminar al único administrador activo.', 'error')
        return redirect(url_for('users.list_users'))
    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f'Usuario {name} eliminado.', 'success')
    return redirect(url_for('users.list_users'))
