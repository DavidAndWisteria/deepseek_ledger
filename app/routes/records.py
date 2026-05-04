from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Record
from app.routes.auth import sanitize_input

records = Blueprint('records', __name__)

@records.route('/')
@login_required
def index():
    user_records = Record.query.filter_by(user_id=current_user.id)\
                        .order_by(Record.date.desc()).limit(50).all()
    income = sum(r.amount for r in user_records if r.record_type == 'income')
    expense = sum(r.amount for r in user_records if r.record_type == 'expense')
    return render_template('dashboard.html', 
                         records=user_records, income=income, expense=expense,
                         balance=income - expense)

@records.route('/add', methods=['POST'])
@login_required
def add_record():
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0
        
    if amount <= 0 or amount > 99999999.99:
        flash('请输入有效的正数金额（最大99999999.99）')
        return redirect(url_for('records.index'))
        
    record_type = request.form.get('record_type', 'expense')
    if record_type not in ['income', 'expense']:
        record_type = 'expense'
        
    record = Record(
        user_id=current_user.id,
        amount=round(amount, 2),
        category=sanitize_input(request.form.get('category', '其他')),
        description=sanitize_input(request.form.get('description', '')),
        record_type=record_type
    )
    db.session.add(record)
    db.session.commit()
    flash('记录添加成功！')
    return redirect(url_for('records.index'))

@records.route('/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = Record.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash('无权删除此记录')
        return redirect(url_for('records.index'))
    db.session.delete(record)
    db.session.commit()
    flash('记录已删除')
    return redirect(url_for('records.index'))