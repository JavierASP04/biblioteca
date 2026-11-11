from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import BOOK_STATUSES, Book, Category
from app.utils import get_or_404, int_field, paginate, text_field

books_bp = Blueprint('books', __name__, url_prefix='/books')


def _book_payload():
    title, error = text_field(
        request.form, 'title', 200, required=True,
        missing='El título es obligatorio.',
        too_long='El título no puede superar 200 caracteres.',
    )
    if error:
        return None, error
    author, error = text_field(
        request.form, 'author', 160, required=True,
        missing='El autor es obligatorio.',
        too_long='El autor no puede superar 160 caracteres.',
    )
    if error:
        return None, error
    isbn, error = text_field(
        request.form, 'isbn', 30,
        too_long='El ISBN no puede superar 30 caracteres.',
    )
    if error:
        return None, error
    editorial, error = text_field(
        request.form, 'editorial', 120,
        too_long='La editorial no puede superar 120 caracteres.',
    )
    if error:
        return None, error
    location, error = text_field(
        request.form, 'location', 80,
        too_long='La ubicación no puede superar 80 caracteres.',
    )
    if error:
        return None, error
    description, error = text_field(
        request.form, 'description', 5000,
        too_long='La descripción no puede superar 5000 caracteres.',
    )
    if error:
        return None, error
    year, error = int_field(
        request.form, 'publication_year', minimum=1000, maximum=2100,
        invalid='El año de publicación no es válido.',
        out_of_range='El año de publicación debe estar entre 1000 y 2100.',
    )
    if error:
        return None, error
    pages, error = int_field(
        request.form, 'pages', minimum=1, maximum=20000,
        invalid='El número de páginas no es válido.',
        out_of_range='El número de páginas debe estar entre 1 y 20000.',
    )
    if error:
        return None, error
    total_copies, error = int_field(
        request.form, 'total_copies', required=True, minimum=1, maximum=10000,
        missing='Indique el número de ejemplares.',
        invalid='El número de ejemplares no es válido.',
        out_of_range='El número de ejemplares debe estar entre 1 y 10000.',
    )
    if error:
        return None, error
    status = request.form.get('status', 'Disponible')
    if status not in BOOK_STATUSES:
        status = 'Disponible'
    category_id, error = int_field(request.form, 'category_id')
    if error:
        return None, error
    if category_id and not db.session.get(Category, category_id):
        return None, 'La categoría seleccionada no existe.'
    return {
        'title': title,
        'author': author,
        'isbn': isbn or None,
        'editorial': editorial,
        'location': location,
        'description': description,
        'publication_year': year,
        'pages': pages,
        'total_copies': total_copies,
        'status': status,
        'category_id': category_id,
    }, None


def _isbn_taken(isbn, book_id=None):
    if not isbn:
        return False
    query = Book.query.filter(db.func.lower(Book.isbn) == isbn.lower())
    if book_id:
        query = query.filter(Book.id != book_id)
    return query.first() is not None


@books_bp.route('/')
@login_required
def list_books():
    query = Book.query
    category_id = request.args.get('category_id')
    status = request.args.get('status')
    search = (request.args.get('search') or '').strip()

    if category_id:
        try:
            query = query.filter_by(category_id=int(category_id))
        except ValueError:
            pass
    if status in BOOK_STATUSES:
        query = query.filter_by(status=status)
    if search:
        term = f'%{search}%'
        query = query.filter(
            Book.title.ilike(term) | Book.author.ilike(term) | Book.isbn.ilike(term)
        )

    pagination = paginate(query.order_by(Book.title))
    categories = Category.query.order_by(Category.name).all()
    stats = {
        'total': Book.query.count(),
        'available': Book.query.filter(Book.available_copies > 0, Book.status == 'Disponible').count(),
        'out': Book.query.filter(Book.available_copies < Book.total_copies).count(),
        'categories': Category.query.count(),
    }
    return render_template(
        'books/list.html',
        books=pagination.items,
        pagination=pagination,
        categories=categories,
        stats=stats,
    )


@books_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_book():
    if request.method == 'POST':
        payload, error = _book_payload()
        if error:
            flash(error, 'error')
        elif _isbn_taken(payload['isbn']):
            flash('Ya existe un libro con ese ISBN.', 'error')
        else:
            book = Book(available_copies=payload['total_copies'], **payload)
            db.session.add(book)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('No se pudo registrar el libro. Revise que el ISBN no esté repetido.', 'error')
            else:
                flash(f'Libro "{book.title}" registrado.', 'success')
                return redirect(url_for('books.detail', id=book.id))
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/form.html', book=None, categories=categories)


@books_bp.route('/<int:id>')
@login_required
def detail(id):
    book = get_or_404(Book, id)
    loans = sorted(book.loans, key=lambda loan: loan.created_at or loan.loan_date, reverse=True)
    return render_template('books/detail.html', book=book, loans=loans)


@books_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_book(id):
    book = get_or_404(Book, id)
    if request.method == 'POST':
        payload, error = _book_payload()
        if error:
            flash(error, 'error')
        elif _isbn_taken(payload['isbn'], book.id):
            flash('Ya existe un libro con ese ISBN.', 'error')
        else:
            borrowed = book.borrowed_copies
            if payload['total_copies'] < borrowed:
                flash(
                    f'No puede dejar {payload["total_copies"]} ejemplares porque hay {borrowed} prestados.',
                    'error',
                )
            else:
                for key, value in payload.items():
                    setattr(book, key, value)
                book.available_copies = payload['total_copies'] - borrowed
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('No se pudo actualizar el libro. Revise que el ISBN no esté repetido.', 'error')
                else:
                    flash(f'Datos del libro "{book.title}" actualizados.', 'success')
                    return redirect(url_for('books.detail', id=book.id))
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/form.html', book=book, categories=categories)


@books_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_book(id):
    book = get_or_404(Book, id)
    if book.loans:
        flash('No se puede eliminar el libro porque tiene préstamos asociados.', 'error')
        return redirect(url_for('books.detail', id=book.id))
    title = book.title
    db.session.delete(book)
    db.session.commit()
    flash(f'Libro "{title}" eliminado.', 'success')
    return redirect(url_for('books.list_books'))


@books_bp.route('/categories', methods=['GET', 'POST'])
@login_required
def list_categories():
    if request.method == 'POST':
        _save_category()
        return redirect(url_for('books.list_categories'))
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/categories.html', categories=categories, editing=None)


@books_bp.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    category = get_or_404(Category, id)
    if request.method == 'POST':
        if _save_category(category):
            return redirect(url_for('books.list_categories'))
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/categories.html', categories=categories, editing=category)


def _save_category(category=None):
    name, error = text_field(
        request.form, 'name', 80, required=True,
        missing='El nombre de la categoría es obligatorio.',
        too_long='El nombre de la categoría no puede superar 80 caracteres.',
    )
    if error:
        flash(error, 'error')
        return False
    description, error = text_field(
        request.form, 'description', 500,
        too_long='La descripción no puede superar 500 caracteres.',
    )
    if error:
        flash(error, 'error')
        return False
    taken = Category.query.filter(db.func.lower(Category.name) == name.lower())
    if category:
        taken = taken.filter(Category.id != category.id)
    if taken.first():
        flash('Ya existe una categoría con ese nombre.', 'error')
        return False
    if category is None:
        category = Category(name=name, description=description)
        db.session.add(category)
        message = f'Categoría "{name}" creada.'
    else:
        category.name = name
        category.description = description
        message = f'Categoría "{name}" actualizada.'
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('No se pudo guardar la categoría.', 'error')
        return False
    flash(message, 'success')
    return True


@books_bp.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = get_or_404(Category, id)
    if category.books:
        flash('No se puede eliminar la categoría porque tiene libros asociados.', 'error')
        return redirect(url_for('books.list_categories'))
    name = category.name
    db.session.delete(category)
    db.session.commit()
    flash(f'Categoría "{name}" eliminada.', 'success')
    return redirect(url_for('books.list_categories'))
