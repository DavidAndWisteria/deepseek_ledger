from typing import cast

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from flask_wtf.csrf import generate_csrf
from sqlalchemy import CursorResult, select, delete, update, func
from app import db
from app.models import Category, CategoryType, BluecoinsCategoryMapping, Transaction

categories = Blueprint('categories', __name__)


@categories.route('/categories')
@login_required
def list_categories():
    """分类列表"""
    stmt = select(Category).order_by(
        Category.category_type,
        Category.category_class,
        Category.category_subclass
    )
    cats = db.session.execute(stmt).scalars().all()
    return render_template('categories.html', categories=cats, category_types=CategoryType)


@categories.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    """添加分类"""
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
    """编辑分类"""
    category = db.session.get(Category, category_id)
    if not category:
        flash('分类不存在')
        return redirect(url_for('categories.list_categories'))
    
    category.category_name = request.form.get('category_name', category.category_name).strip()
    category.category_other_name = request.form.get('category_other_name', '').strip() or None
    category.category_class = request.form.get('category_class', category.category_class).strip()
    category.category_subclass = request.form.get('category_subclass', '').strip()
    category.category_type = CategoryType(request.form.get('category_type', category.category_type.value))
    
    db.session.commit()
    flash('分类更新成功')
    return redirect(url_for('categories.list_categories'))


@categories.route('/categories/<int:category_id>/check-delete')
@login_required
def check_delete_category(category_id):
    """检查分类关联交易（AJAX）"""
    category = db.session.get(Category, category_id)
    if not category:
        return '<p style="color: #e74c3c; text-align: center;">分类不存在</p>'
    
    # 使用 select 计数替代 Transaction.query.filter_by(...).count()
    count_stmt = select(func.count()).select_from(Transaction).where(
        Transaction.trans_category_id == category_id
    )
    transaction_count = db.session.scalar(count_stmt)
    
    csrf_token = generate_csrf()
    
    if transaction_count == 0:
        return f'''<div id="delete-content-data">
            <p style="text-align: center; margin-bottom: 16px;">该分类没有关联交易，可以安全删除。</p>
            <form method="POST" action="{url_for('categories.confirm_delete_category', category_id=category_id)}">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <input type="hidden" name="action" value="delete">
                <div style="display: flex; gap: 12px; justify-content: center;">
                    <button type="submit" class="btn btn-danger">确认删除</button>
                    <button type="button" class="btn btn-secondary" onclick="closeDeleteModal()">取消</button>
                </div>
            </form>
        </div>'''
    
    # 获取所有分类，排除自身
    stmt = select(Category).order_by(
        Category.category_type,
        Category.category_class,
        Category.category_subclass
    )
    cats = db.session.execute(stmt).scalars().all()
    target_categories = [c for c in cats if c.category_id != category_id]
    
    html = f'''<div id="delete-content-data">
    <p style="margin-bottom: 12px;">分类 <strong>"{category.category_name}"</strong> 有 <strong>{transaction_count}</strong> 笔关联交易。</p>
    <p style="color: #888; font-size: 13px; margin-bottom: 16px;">请选择如何处理这些交易：</p>
    
    <form method="POST" action="{url_for('categories.confirm_delete_category', category_id=category_id)}">
        <input type="hidden" name="csrf_token" value="{csrf_token}">
        
        <div class="form-group" style="padding: 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 12px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="radio" name="action" value="delete" checked onchange="toggleTargetSelect()">
                <span>🗑 <strong>删除所有关联交易</strong>（不可恢复）</span>
            </label>
        </div>
        
        <div class="form-group" style="padding: 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 16px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="radio" name="action" value="migrate" onchange="toggleTargetSelect()">
                <span>📦 <strong>迁移到另一个分类</strong></span>
            </label>
            <select name="target_category_id" id="target-category-select" style="margin-top: 8px; display: none;">
                <option value="">选择目标分类</option>'''
    
    for c in target_categories:
        html += f'<option value="{c.category_id}">{c.category_class} › {c.category_subclass or "-"} › {c.category_name} ({c.category_type.value})</option>'
    
    html += '''</select>
        </div>
        
        <div style="display: flex; gap: 12px;">
            <button type="submit" class="btn btn-danger">⚠ 确认删除</button>
            <button type="button" class="btn btn-secondary" onclick="closeDeleteModal()">取消</button>
        </div>
    </form>
</div>

<script>
    function toggleTargetSelect() {
        const migrateRadio = document.querySelector('input[value="migrate"]');
        const select = document.getElementById("target-category-select");
        select.style.display = migrateRadio.checked ? "block" : "none";
        select.required = migrateRadio.checked;
    }
</script>'''
    
    return html


@categories.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    """删除分类（无关联交易时直接删除，否则跳转弹窗）"""
    category = db.session.get(Category, category_id)
    if not category:
        flash('分类不存在')
        return redirect(url_for('categories.list_categories'))
    
    # 检查关联交易数量
    count_stmt = select(func.count()).select_from(Transaction).where(
        Transaction.trans_category_id == category_id
    )
    transaction_count = db.session.scalar(count_stmt) or 0
    
    if transaction_count > 0:
        flash(f'分类 "{category.category_name}" 有 {transaction_count} 笔关联交易，请通过列表中的删除按钮处理')
        return redirect(url_for('categories.list_categories'))
    
    # 删除 Bluecoins 映射
    del_mapping_stmt = delete(BluecoinsCategoryMapping).where(
        BluecoinsCategoryMapping.category_id == category_id
    )
    db.session.execute(del_mapping_stmt)
    
    db.session.delete(category)
    db.session.commit()
    flash('分类已删除')
    return redirect(url_for('categories.list_categories'))


@categories.route('/categories/<int:category_id>/delete/confirm', methods=['POST'])
@login_required
def confirm_delete_category(category_id):
    """确认删除分类（处理关联交易）"""
    category = db.session.get(Category, category_id)
    if not category:
        flash('分类不存在')
        return redirect(url_for('categories.list_categories'))
    
    action = request.form.get('action', 'delete')
    
    if action == 'migrate':
        target_category_id = request.form.get('target_category_id', type=int)
        target = db.session.get(Category, target_category_id)
        if not target:
            flash('目标分类无效')
            return redirect(url_for('categories.list_categories'))
        
        # 迁移交易：更新 trans_category_id
        upd_stmt = (
            update(Transaction)
            .where(Transaction.trans_category_id == category_id)
            .values(trans_category_id=target_category_id)
        )
        result = cast(CursorResult, db.session.execute(upd_stmt))
        updated = result.rowcount
        flash(f'已将 {updated} 笔交易迁移到 "{target.category_name}"')
    else:
        # 删除所有关联交易，包括转账配对
        trans_stmt = select(Transaction).where(
            Transaction.trans_category_id == category_id
        )
        transactions = db.session.execute(trans_stmt).scalars().all()
        deleted = len(transactions)
        for t in transactions:
            if t.trans_counter_id:
                counter = db.session.get(Transaction, t.trans_counter_id)
                if counter:
                    db.session.delete(counter)
            db.session.delete(t)
        flash(f'已删除 {deleted} 笔关联交易')
    
    # 删除 Bluecoins 映射
    del_mapping_stmt = delete(BluecoinsCategoryMapping).where(
        BluecoinsCategoryMapping.category_id == category_id
    )
    db.session.execute(del_mapping_stmt)
    
    db.session.delete(category)
    db.session.commit()
    flash('分类已删除')
    return redirect(url_for('categories.list_categories'))