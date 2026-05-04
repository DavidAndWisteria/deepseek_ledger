from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models import Category, CategoryType

categories = Blueprint('categories', __name__)


@categories.route('/categories')
@login_required
def list_categories():
    cats = Category.query.order_by(Category.category_type, Category.category_class).all()
    return render_template('categories.html', categories=cats, category_types=CategoryType)


@categories.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('category_name', '')
    cls = request.form.get('category_class', '')
    subclass = request.form.get('category_subclass', '')
    ctype = request.form.get('category_type', 'E')
    
    if not name or not cls:
        flash('请填写分类名称和大类')
        return redirect(url_for('categories.list_categories'))
    
    category = Category(
        category_name=name,
        category_class=cls,
        category_subclass=subclass,
        category_type=CategoryType[ctype]
    )
    db.session.add(category)
    db.session.commit()
    flash('分类添加成功')
    return redirect(url_for('categories.list_categories'))


@categories.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash('分类已删除')
    return redirect(url_for('categories.list_categories'))