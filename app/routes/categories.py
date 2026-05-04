from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models import Category, CategoryType

categories = Blueprint('categories', __name__)


@categories.route('/categories')
@login_required
def list_categories():
    cats = Category.query.order_by(Category.category_type, Category.category_class, Category.category_subclass).all()
    return render_template('categories.html', categories=cats, category_types=CategoryType)


@categories.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('category_name', '').strip()
    other_name = request.form.get('category_other_name', '').strip()
    cls = request.form.get('category_class', '').strip()
    subclass = request.form.get('category_subclass', '').strip()
    ctype = request.form.get('category_type', 'E')
    
    if not name:
        flash('请填写分类名称')
        return redirect(url_for('categories.list_categories'))
    if not cls:
        flash('请填写大类')
        return redirect(url_for('categories.list_categories'))
    
    category = Category(
        category_name=name,
        category_other_name=other_name if other_name else None,
        category_class=cls,
        category_subclass=subclass if subclass else '',
        category_type=CategoryType(ctype)
    )
    db.session.add(category)
    db.session.commit()
    flash('分类添加成功')
    return redirect(url_for('categories.list_categories'))


@categories.route('/categories/<int:category_id>/edit', methods=['POST'])
@login_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    category.category_name = request.form.get('category_name', category.category_name).strip()
    category.category_other_name = request.form.get('category_other_name', '').strip() or None
    category.category_class = request.form.get('category_class', category.category_class).strip()
    category.category_subclass = request.form.get('category_subclass', '').strip()
    category.category_type = CategoryType(request.form.get('category_type', category.category_type.value))
    
    db.session.commit()
    flash('分类更新成功')
    return redirect(url_for('categories.list_categories'))


@categories.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash('分类已删除')
    return redirect(url_for('categories.list_categories'))