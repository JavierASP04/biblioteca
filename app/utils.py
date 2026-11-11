import csv
import re
from datetime import datetime
from functools import wraps
from io import StringIO
from zoneinfo import ZoneInfo

from flask import Response, abort, current_app, flash, redirect, request, url_for
from flask_login import current_user

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PER_PAGE = 20


def get_or_404(model, ident):
    from app import db
    obj = db.session.get(model, ident)
    if obj is None:
        abort(404)
    return obj


def school_today():
    tzname = current_app.config.get('SCHOOL_TZ', 'America/Caracas')
    try:
        return datetime.now(ZoneInfo(tzname)).date()
    except Exception:
        return datetime.now().date()


def clean(value):
    if value is None:
        return ''
    return str(value).strip()


def parse_int(value, default=None):
    if value in (None, ''):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def text_field(form, field, limit, *, required=False, missing='Este dato es obligatorio.', too_long='El texto es demasiado largo.'):
    value = clean(form.get(field))
    if not value:
        if required:
            return None, missing
        return None, None
    if len(value) > limit:
        return None, too_long
    return value, None


def int_field(form, field, *, required=False, minimum=None, maximum=None,
              missing='Este valor es obligatorio.',
              invalid='El valor numérico no es válido.',
              out_of_range='El valor está fuera del rango permitido.'):
    raw = clean(form.get(field))
    if not raw:
        if required:
            return None, missing
        return None, None
    try:
        number = int(raw)
    except ValueError:
        return None, invalid
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        return None, out_of_range
    return number, None


def optional_email(form, field='email'):
    value = clean(form.get(field)).lower()
    if not value:
        return None, None
    if not EMAIL_RE.match(value) or len(value) > 120:
        return None, 'El correo electrónico no es válido.'
    return value, None


def safe_next_url(target):
    if not target or not isinstance(target, str):
        return None
    target = target.strip()
    if not target.startswith('/') or target.startswith('//'):
        return None
    if any(char in target for char in '\\<>\r\n\x00'):
        return None
    return target


def paginate(query):
    page = parse_int(request.args.get('page'), 1) or 1
    return query.paginate(page=max(page, 1), per_page=PER_PAGE, error_out=False)


def csv_cell(value):
    if value is None:
        return ''
    text = str(value)
    if text[:1] in ('=', '+', '-', '@'):
        return "'" + text
    return text


def csv_download(filename, header, rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([csv_cell(item) for item in header])
    for row in rows:
        writer.writerow([csv_cell(item) for item in row])
    payload = '\ufeff' + buffer.getvalue()
    response = Response(payload, mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        if current_user.role != 'Administrador':
            flash('Solo un administrador puede acceder a esta sección.', 'error')
            return redirect(url_for('main.dashboard'))
        return view(*args, **kwargs)
    return wrapped
