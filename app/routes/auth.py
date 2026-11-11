from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import User
from app.utils import safe_next_url, text_field

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    next_url = safe_next_url(request.args.get('next')) or safe_next_url(request.form.get('next'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                logout_user()
                flash('Esta cuenta está desactivada. Contacte al administrador.', 'error')
                return render_template('login.html', next_url=next_url)
            login_user(user, remember=bool(request.form.get('remember')))
            flash(f'Bienvenido, {user.name}', 'success')
            return redirect(next_url or url_for('main.dashboard'))
        flash('Correo o contraseña incorrectos.', 'error')

    return render_template('login.html', next_url=next_url)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/cuenta', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        name, error = text_field(
            request.form,
            'name',
            100,
            required=True,
            missing='El nombre es obligatorio.',
            too_long='El nombre no puede superar 100 caracteres.',
        )
        if error:
            flash(error, 'error')
            return render_template('account/form.html')

        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        if current_password or new_password or confirm_password:
            if not current_user.check_password(current_password):
                flash('La contraseña actual no es correcta.', 'error')
                return render_template('account/form.html')
            if len(new_password) < 8:
                flash('La nueva contraseña debe tener al menos 8 caracteres.', 'error')
                return render_template('account/form.html')
            if new_password != confirm_password:
                flash('La confirmación de la contraseña no coincide.', 'error')
                return render_template('account/form.html')
            current_user.set_password(new_password)

        current_user.name = name
        db.session.commit()
        flash('Sus datos fueron actualizados.', 'success')
        return redirect(url_for('auth.account'))

    return render_template('account/form.html')
