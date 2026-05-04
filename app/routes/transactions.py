from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Transaction, Account, Category, Owner, CategoryType

transactions = Blueprint('transactions', __name__)


def get_user_owner():
    """获取当前用户的Owner"""
    if current_user.owner:
        return current_user.owner
    return None


def get_visible_transactions_query(start_date=None, end_date=None):
    """获取当前用户可见的交易查询"""
    owner = get_user_owner()
    if not owner:
        return Transaction.query.filter(False)  # 返回空查询
    
    query = Transaction.query
    
    if current_user.can_view_family_data():
        # 成人可看家庭所有交易
        family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
        query = query.filter(Transaction.trans_owner_id.in_(family_owner_ids))
    else:
        # 小孩只能看自己的
        query = query.filter_by(trans_owner_id=owner.owner_id)
    
    if start_date:
        query = query.filter(Transaction.trans_datetime >= start_date)
    if end_date:
        query = query.filter(Transaction.trans_datetime <= end_date)
    
    return query.order_by(Transaction.trans_datetime.desc())


@transactions.route('/')
@login_required
def dashboard():
    """仪表盘"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('auth.login'))
    
    # 默认显示本月
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    start_date = request.args.get('start_date', start_of_month.strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', end_of_month.strftime('%Y-%m-%d'))
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError:
        start = start_of_month
        end = end_of_month
    
    transactions_list = get_visible_transactions_query(start, end).all()
    
    # 统计
    total_income = sum(t.trans_amount for t in transactions_list if t.is_income())
    total_expense = sum(abs(t.trans_amount) for t in transactions_list if t.is_expense())
    total_transfer = sum(abs(t.trans_amount) for t in transactions_list if t.is_transfer())
    
    accounts = Account.query.filter_by(account_owner_id=owner.owner_id).all()
    categories = Category.query.all()
    
    return render_template(
        'dashboard.html',
        transactions=transactions_list,
        accounts=accounts,
        categories=categories,
        total_income=total_income,
        total_expense=total_expense,
        total_transfer=total_transfer,
        balance=total_income - total_expense,
        start_date=start_date,
        end_date=end_date
    )


@transactions.route('/add', methods=['POST'])
@login_required
def add_transaction():
    """添加交易"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('transactions.dashboard'))
    
    trans_type = request.form.get('trans_type')
    account_id = request.form.get('account_id', type=int)
    category_id = request.form.get('category_id', type=int)
    amount = request.form.get('amount', type=float)
    description = request.form.get('description', '')
    trans_date = request.form.get('trans_date', '')
    
    # 验证
    if not account_id or not category_id or not amount:
        flash('请填写完整信息')
        return redirect(url_for('transactions.dashboard'))
    
    if amount <= 0:
        flash('金额必须大于0')
        return redirect(url_for('transactions.dashboard'))
    
    try:
        trans_datetime = datetime.strptime(trans_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        trans_datetime = datetime.now(timezone.utc)
    
    category = Category.query.get(category_id)
    account = Account.query.get(account_id)
    
    if not category or not account:
        flash('无效的分类或账户')
        return redirect(url_for('transactions.dashboard'))
    
    if trans_type == 'income':
        # 收入：正金额
        transaction = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=description,
            trans_amount=amount,
            trans_account_id=account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id
        )
        db.session.add(transaction)
    
    elif trans_type == 'expense':
        # 支出：负金额
        transaction = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=description,
            trans_amount=-amount,
            trans_account_id=account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id
        )
        db.session.add(transaction)
    
    elif trans_type == 'transfer':
        to_account_id = request.form.get('to_account_id', type=int)
        if not to_account_id or to_account_id == account_id:
            flash('请选择不同的转出和转入账户')
            return redirect(url_for('transactions.dashboard'))
        
        # 转出记录（负金额）
        trans_out = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=f'转出: {description}',
            trans_amount=-amount,
            trans_account_id=account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id
        )
        db.session.add(trans_out)
        db.session.flush()
        
        # 转入记录（正金额）
        trans_in = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=f'转入: {description}',
            trans_amount=amount,
            trans_account_id=to_account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id,
            trans_counter_id=trans_out.trans_id
        )
        db.session.add(trans_in)
        db.session.flush()
        
        # 更新转出记录的counter_id
        trans_out.trans_counter_id = trans_in.trans_id
        db.session.add(trans_out)
    
    db.session.commit()
    flash('交易添加成功')
    return redirect(url_for('transactions.dashboard'))


@transactions.route('/delete/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    """删除交易"""
    transaction = Transaction.query.get_or_404(trans_id)
    
    # 权限检查
    owner = get_user_owner()
    if not owner or transaction.trans_owner_id != owner.owner_id:
        flash('无权删除此交易')
        return redirect(url_for('transactions.dashboard'))
    
    # 如果是转账，同时删除配对记录
    if transaction.trans_counter_id:
        counter = Transaction.query.get(transaction.trans_counter_id)
        if counter:
            db.session.delete(counter)
    
    db.session.delete(transaction)
    db.session.commit()
    flash('交易已删除')
    return redirect(url_for('transactions.dashboard'))