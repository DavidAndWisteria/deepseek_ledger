from datetime import datetime, timezone, timedelta
from typing import Any
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from sqlalchemy import select, delete, false
from sqlalchemy.orm import selectinload
from app import db
from app.models import (Transaction, Account, Category, Owner, TransactionStatus,
                         AccountBalance, TimeDeposit, DepositStatus)
from app.routes.accounts import get_fx_rate_to_hkd

transactions = Blueprint('transactions', __name__)

# 定期存款 / 货币联系存款账户类型（开立/到期触发存款记录流程）
DEPOSIT_ACCOUNT_TYPES = ('TIME_DEPOSIT', 'CURRENCY_LINKED_DEPOSIT')


def invalidate_account_balances(account_id, from_datetime):
    """删除指定账户从指定日期起的所有缓存日终余额记录"""
    if not account_id:
        return
    stmt = (
        delete(AccountBalance)
        .where(
            AccountBalance.account_id == account_id,
            AccountBalance.as_of_dt >= from_datetime.date()
        )
    )
    db.session.execute(stmt)


def _ensure_utc(dt):
    """确保datetime带UTC时区信息，用于安全比较"""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _fx_unit_kwargs(currency, amount, stored_fx_rate):
    """外汇字段：trans_fx_amount 存外汇金额，trans_fx_rate 存汇率，trans_fx_currency_name 存外汇货币名"""
    return {
        'trans_fx_amount': amount,
        'trans_fx_rate': stored_fx_rate,
        'trans_fx_currency_name': currency,
        'trans_is_rhs_currency_ind': True,
    }


def _fund_unit_kwargs(unit, unit_price):
    """投资单位字段：trans_unit 存份额，trans_unit_price 存单价"""
    return {
        'trans_unit': unit,
        'trans_unit_price': unit_price,
        'trans_unit_name': None,
    }


def _apply_side_units(txn, account, amount, prefix):
    """转账编辑：保存单侧（转出/转入）单位与单价，返回错误提示或 None

    prefix 为 'out'/'in'，分别对应表单 out_unit / in_unit。
    仅对有单位概念账户生效；单位 × 单价 = 账户默认货币金额（HKD 账户强校验）。
    """
    unit = request.form.get(f'{prefix}_unit', type=float)
    unit_price = request.form.get(f'{prefix}_unit_price', type=float)
    if not account or not account.account_has_unit_ind:
        txn.trans_unit = None
        txn.trans_unit_price = None
        txn.trans_unit_name = None
        return None

    has_unit = unit is not None
    has_up = unit_price is not None
    if has_unit and has_up:
        amount_from_units = round(unit * unit_price, 2)
        if account.account_currency_name == 'HKD' and abs(amount - amount_from_units) > 0.02:
            return f'单位×单价 ({unit} × {unit_price} ≈ {amount_from_units}) 与金额 ({amount}) 不符'
    elif has_unit:
        unit_price = round(amount / unit, 6)
    elif has_up:
        unit = round(amount / unit_price, 6)

    if unit is not None and unit_price is not None:
        sign = -1 if prefix == 'out' else 1
        txn.trans_unit = sign * unit
        txn.trans_unit_price = unit_price
        txn.trans_unit_name = None
    else:
        txn.trans_unit = None
        txn.trans_unit_price = None
        txn.trans_unit_name = None
    return None


def get_user_owner():
    """获取当前用户的Owner"""
    if current_user.owner:
        return current_user.owner
    return None


def get_visible_transactions_query(start_date=None, end_date=None, status_filter=None, 
                                   category_id=None, account_id=None):
    """
    返回一个针对当前用户可见交易的 SELECT 语句。
    调用方需通过 db.session.execute(stmt).scalars().all() 获取结果。
    """
    owner = get_user_owner()
    if not owner:
        # 无条件返回空结果
        return select(Transaction).where(false())

    stmt = select(Transaction)

    if current_user.can_view_family_data():
        # 获取家庭成员的所有 owner_id
        family_owner_ids = db.session.execute(
            select(Owner.owner_id).where(Owner.family_id == owner.family_id)
        ).scalars().all()
        stmt = stmt.where(Transaction.trans_owner_id.in_(family_owner_ids))
    else:
        stmt = stmt.where(Transaction.trans_owner_id == owner.owner_id)

    if start_date:
        stmt = stmt.where(Transaction.trans_datetime >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.trans_datetime <= end_date)

    if status_filter:
        stmt = stmt.where(Transaction.trans_status == TransactionStatus(status_filter))

    if category_id:
        stmt = stmt.where(Transaction.trans_category_id == category_id)

    if account_id:
        stmt = stmt.where(Transaction.trans_account_id == account_id)

    return stmt.order_by(Transaction.trans_datetime.desc())


def _get_filter_params():
    """从 request.args 或 request.form 获取当前筛选参数"""
    def get_param(key):
        return request.args.get(key, request.form.get(key, ''))

    return {
        k: v for k, v in {
            'start_date': get_param('start_date'),
            'end_date': get_param('end_date'),
            'status': get_param('status'),
            'category_id': get_param('category_id'),
            'account_id': get_param('account_id'),
            'from_accounts': get_param('from_accounts'),
        }.items() if v
    }


def _dashboard_redirect(**extra):
    """重定向到仪表盘，保留筛选参数，默认显示列表标签页"""
    params: dict[str, Any] = {'tab': 'list-tab'}
    params.update(_get_filter_params())
    params.update(extra)
    return redirect(url_for('transactions.dashboard', **params))


@transactions.route('/')
@login_required
def dashboard():
    """仪表盘 - 显示交易列表和统计"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('auth.login'))
    
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    start_date = request.args.get('start_date', '') or session.get('dash_start_date', start_of_month.strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', '') or session.get('dash_end_date', end_of_month.strftime('%Y-%m-%d'))
    status_filter = request.args.get('status', '') or session.get('dash_status', '')
    category_id = request.args.get('category_id', type=int) or session.get('dash_category_id')
    _request_account_id = request.args.get('account_id', type=int)
    if _request_account_id is not None:
        account_id = _request_account_id
    elif any(request.args.get(k) for k in ('start_date', 'end_date', 'status', 'category_id')):
        account_id = None
    else:
        account_id = session.get('dash_account_id')
    from_accounts = request.args.get('from_accounts', '')
    active_tab = request.args.get('tab', 'add-tab')

    # Persist filters to session for cross-page navigation
    session['dash_start_date'] = start_date
    session['dash_end_date'] = end_date
    session['dash_status'] = status_filter
    session['dash_category_id'] = category_id
    session['dash_account_id'] = account_id
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError:
        start = start_of_month
        end = end_of_month
    
    # 执行查询
    stmt = get_visible_transactions_query(
        start, end, status_filter, category_id, account_id
    )
    stmt = stmt.options(selectinload(Transaction.counter_transaction))
    transactions_list = db.session.execute(stmt).scalars().all()
    
    total_income = sum(t.trans_amount for t in transactions_list if t.is_income())
    total_expense = sum(abs(t.trans_amount) for t in transactions_list if t.is_expense())
    total_transfer = sum(abs(t.trans_amount) for t in transactions_list if t.is_transfer())
    unverified_count = sum(1 for t in transactions_list if t.trans_status == TransactionStatus.UNVERIFIED)
    
    # 按天分组
    daily_groups = {}
    for t in transactions_list:
        day_key = t.trans_datetime.strftime('%Y-%m-%d')
        if day_key not in daily_groups:
            daily_groups[day_key] = {
                'date': t.trans_datetime,
                'transactions': [],
                'income': 0.0,
                'expense': 0.0
            }
        daily_groups[day_key]['transactions'].append(t)
        if t.is_income():
            daily_groups[day_key]['income'] += t.trans_amount
        elif t.is_expense():
            daily_groups[day_key]['expense'] += abs(t.trans_amount)
    
    daily_sorted = sorted(daily_groups.values(), key=lambda x: x['date'], reverse=True)
    
    # 账户查询
    account_stmt = (
        select(Account)
        .where(Account.account_owner_id == owner.owner_id)
        .order_by(Account.account_type, Account.account_custodian, 
                  Account.account_owner_id, Account.account_name)
    )
    accounts = db.session.execute(account_stmt).scalars().all()
    
    # 分类查询
    category_stmt = (
        select(Category)
        .order_by(Category.category_class, Category.category_subclass, Category.category_name)
    )
    categories = db.session.execute(category_stmt).scalars().all()
    
    # 定期存款/货币联系存款流程上下文（添加转账交易后弹出填写/确认窗口）
    deposit_flow = request.args.get('deposit_flow', '')
    deposit_data = None
    in_progress_deposits = []
    if deposit_flow in ('open', 'mature'):
        _dep_account = db.session.get(Account, request.args.get('deposit_account_id', type=int))
        deposit_data = {
            'trans_id': request.args.get('deposit_trans_id', type=int),
            'account_id': request.args.get('deposit_account_id', type=int),
            'account_type': request.args.get('deposit_account_type', ''),
            'account_name': _dep_account.account_name if _dep_account else '',
            'currency': request.args.get('deposit_currency', ''),
            'amount': request.args.get('deposit_amount', type=float),
            'date': request.args.get('deposit_date', ''),
        }
        if deposit_flow == 'mature' and deposit_data['account_id']:
            dep_stmt = (
                select(TimeDeposit)
                .where(
                    TimeDeposit.status == DepositStatus.IN_PROGRESS,
                    TimeDeposit.account_id == deposit_data['account_id']
                )
                .order_by(TimeDeposit.subscription_date.desc(), TimeDeposit.deposit_id.desc())
            )
            in_progress_deposits = db.session.execute(dep_stmt).scalars().all()
    
    return render_template(
        'dashboard.html',
        daily_sorted=daily_sorted,
        accounts=accounts,
        categories=categories,
        total_income=total_income,
        total_expense=total_expense,
        total_transfer=total_transfer,
        balance=total_income - total_expense,
        unverified_count=unverified_count,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
        category_filter=category_id or '',
        account_filter=account_id or '',
        from_accounts=from_accounts,
        active_tab=active_tab,
        deposit_flow=deposit_flow,
        deposit_data=deposit_data,
        in_progress_deposits=in_progress_deposits,
    )


@transactions.route('/add', methods=['POST'])
@login_required
def add_transaction():
    """添加交易 - 支持收入、支出、转账"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('transactions.dashboard'))
    
    trans_type = request.form.get('trans_type')
    account_id = request.form.get('account_id', type=int)
    category_id = request.form.get('category_id', type=int)
    amount = request.form.get('amount', type=float)
    currency = request.form.get('currency', 'HKD')
    description = request.form.get('description', '')
    trans_date = request.form.get('trans_date', '')
    trans_time = request.form.get('trans_time', '00:00')
    
    if not account_id or not category_id or not amount:
        flash('请填写完整信息')
        return redirect(url_for('transactions.dashboard'))

    if amount <= 0:
        flash('金额必须大于0')
        return redirect(url_for('transactions.dashboard'))

    try:
        trans_datetime = datetime.strptime(
            f'{trans_date} {trans_time}', '%Y-%m-%d %H:%M'
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        trans_datetime = datetime.now(timezone.utc)

    category = db.session.get(Category, category_id)
    account = db.session.get(Account, account_id)

    if not category or not account:
        flash('无效的分类或账户')
        return redirect(url_for('transactions.dashboard'))

    unit = request.form.get('unit', type=float)
    unit_price = request.form.get('unit_price', type=float)
    has_unit_concept = account.account_has_unit_ind
    show_units = (
        has_unit_concept or 
        currency != 'HKD'
    )

    if not show_units:
        unit = None
        unit_price = None

    fx_rate_input = None
    fx_auto = False
    is_fx = (currency != 'HKD' and trans_type != 'transfer')
    stored_fx_rate = 0.0  # will init in certain branch
    effective_rate = 1.0
    to_account_id = 0  # will init in certain branch

    if currency != 'HKD' and trans_type != 'transfer':
        fx_rate_input = request.form.get('fx_rate', type=float)
        fx_auto = request.form.get('fx_auto', '0') == '1'
        if fx_rate_input is None:
            fx_rate_input = 0.0

        spot_rate = get_fx_rate_to_hkd(currency, trans_datetime.date())
        inv_spot_rate = 1.0 / spot_rate
        effective_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else inv_spot_rate
        stored_fx_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else 0.0

    if has_unit_concept:
        # 有单位概念的账户（如基金）：单位 = 份额，单位单价 = 账户默认货币单价（如 USD 基金单价为 USD）
        has_unit = unit is not None
        has_unit_price = unit_price is not None
        if has_unit and has_unit_price:
            amount_from_units = round(unit * unit_price, 2)
            if abs(amount - amount_from_units) > 0.02:
                flash(f'单位×单价 ({unit} × {unit_price} ≈ {amount_from_units}) 与金额 ({amount}) 不符')
                return redirect(url_for('transactions.dashboard'))
        elif has_unit:
            unit_price = round(amount / unit, 6)
        elif has_unit_price:
            unit = round(amount / unit_price, 6)
        hkd_amount = round(amount / effective_rate, 2) if currency != 'HKD' else amount
    elif show_units:
        # 非单位账户的外汇：单位 = 外汇金额，单位单价 = 每单位 HKD 价格
        hkd_amount = round(amount / effective_rate, 2) if is_fx else amount
        has_amount = True
        has_unit = unit is not None
        has_unit_price = unit_price is not None
        if has_unit and has_unit_price:
            hkd_from_units = round(unit * unit_price, 2)
            if has_amount and unit_price > 0:
                if abs(hkd_amount - hkd_from_units) > 0.02:
                    flash(f'单位×单价 ({unit} × {unit_price} ≈ {hkd_from_units}) 与交易金额 ({hkd_amount}) 不符')
                    return redirect(url_for('transactions.dashboard'))
            else:
                hkd_amount = hkd_from_units
                if not is_fx:
                    amount = hkd_amount
        elif has_unit and has_amount:
            unit_price = round(hkd_amount / unit, 6)
        elif has_unit_price and has_amount:
            unit = round(hkd_amount / unit_price, 6)
    else:
        hkd_amount = amount

    if trans_type == 'income':
        kwargs = {
            'trans_datetime': trans_datetime,
            'trans_desc': description,
            'trans_amount': hkd_amount,
            'trans_currency_name': 'HKD' if is_fx else currency,
            'trans_account_id': account_id,
            'trans_category_id': category_id,
            'trans_owner_id': owner.owner_id,
        }
        if has_unit_concept and unit is not None and unit_price is not None:
            kwargs.update(_fund_unit_kwargs(unit, unit_price))
        elif is_fx:
            kwargs.update(_fx_unit_kwargs(currency, amount, stored_fx_rate))
        transaction = Transaction(**kwargs)
        db.session.add(transaction)

    elif trans_type == 'expense':
        kwargs = {
            'trans_datetime': trans_datetime,
            'trans_desc': description,
            'trans_amount': -hkd_amount,
            'trans_currency_name': 'HKD' if is_fx else currency,
            'trans_account_id': account_id,
            'trans_category_id': category_id,
            'trans_owner_id': owner.owner_id,
        }
        if has_unit_concept and unit is not None and unit_price is not None:
            kwargs.update(_fund_unit_kwargs(-unit, unit_price))
        elif is_fx:
            kwargs.update(_fx_unit_kwargs(currency, -amount, stored_fx_rate))
        transaction = Transaction(**kwargs)
        db.session.add(transaction)

    elif trans_type == 'special':
        kwargs = {
            'trans_datetime': trans_datetime,
            'trans_desc': description,
            'trans_amount': hkd_amount,
            'trans_currency_name': 'HKD' if is_fx else currency,
            'trans_account_id': account_id,
            'trans_category_id': category_id,
            'trans_owner_id': owner.owner_id,
        }
        if has_unit_concept and unit is not None and unit_price is not None:
            kwargs.update(_fund_unit_kwargs(unit, unit_price))
        elif is_fx:
            kwargs.update(_fx_unit_kwargs(currency, amount, stored_fx_rate))
        transaction = Transaction(**kwargs)
        db.session.add(transaction)
    
    elif trans_type == 'transfer':
        to_account_id = request.form.get('to_account_id', type=int)
        to_currency = request.form.get('to_currency', currency)
        to_amount = request.form.get('to_amount', type=float)
        if to_amount is None or to_amount <= 0:
            to_amount = amount
        if not to_account_id or to_account_id == account_id:
            flash('请选择不同的转出和转入账户')
            return redirect(url_for('transactions.dashboard'))
        
        trans_out = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=f'转出: {description}',
            trans_amount=-amount,
            trans_currency_name=currency,
            trans_account_id=account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id
        )
        if has_unit_concept and unit is not None and unit_price is not None:
            trans_out.trans_unit = -unit
            trans_out.trans_unit_price = unit_price
            trans_out.trans_unit_name = None
        db.session.add(trans_out)
        db.session.flush()
        
        trans_in = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=f'转入: {description}',
            trans_amount=to_amount,
            trans_currency_name=to_currency,
            trans_account_id=to_account_id,
            trans_category_id=category_id,
            trans_owner_id=owner.owner_id,
            trans_counter_id=trans_out.trans_id
        )
        db.session.add(trans_in)
        db.session.flush()
        
        trans_out.trans_counter_id = trans_in.trans_id
        db.session.add(trans_out)
    
    invalidate_account_balances(account_id, trans_datetime)
    if trans_type == 'transfer':
        invalidate_account_balances(to_account_id, trans_datetime)
    
    db.session.commit()
    flash('交易添加成功')

    # 定期存款/货币联系存款流程：转账到存款账户 → 开立；转账从存款账户 → 到期
    if trans_type == 'transfer':
        to_account = db.session.get(Account, to_account_id)
        from_account_type = account.account_type.value
        to_account_type = to_account.account_type.value if to_account else ''
        deposit_params = {
            'tab': 'list-tab',
            'deposit_trans_id': trans_out.trans_id,
            'deposit_account_id': to_account_id,
            'deposit_currency': to_currency,
            'deposit_amount': to_amount,
            'deposit_date': trans_date,
        }
        if to_account_type in DEPOSIT_ACCOUNT_TYPES:
            deposit_params.update({
                'deposit_flow': 'open',
                'deposit_account_type': to_account_type,
            })
            return redirect(url_for('transactions.dashboard', **deposit_params))
        if from_account_type in DEPOSIT_ACCOUNT_TYPES:
            deposit_params.update({
                'deposit_flow': 'mature',
                'deposit_account_id': account_id,
                'deposit_currency': currency,
                'deposit_amount': amount,
            })
            return redirect(url_for('transactions.dashboard', **deposit_params))

    return _dashboard_redirect()


@transactions.route('/delete/<int:trans_id>', methods=['POST'])
@login_required
def delete_transaction(trans_id):
    """删除交易 - 如果是转账则同时删除配对记录"""
    transaction = db.session.get(Transaction, trans_id)
    if not transaction:
        flash('交易不存在')
        return _dashboard_redirect()
    
    owner = get_user_owner()
    if not owner or transaction.trans_owner_id != owner.owner_id:
        flash('无权删除此交易')
        return _dashboard_redirect()
    
    affected_account_ids = {transaction.trans_account_id}
    affected_datetime = transaction.trans_datetime
    
    if transaction.trans_counter_id:
        counter = db.session.get(Transaction, transaction.trans_counter_id)
        if counter:
            affected_account_ids.add(counter.trans_account_id)
            if counter.trans_datetime < affected_datetime:
                affected_datetime = counter.trans_datetime
            db.session.delete(counter)
    
    db.session.delete(transaction)
    
    for acct_id in affected_account_ids:
        invalidate_account_balances(acct_id, affected_datetime)
    
    db.session.commit()
    flash('交易已删除')
    return _dashboard_redirect()


@transactions.route('/status/<int:trans_id>/<status>', methods=['POST'])
@login_required
def update_status(trans_id, status):
    """更新单笔交易状态"""
    transaction = db.session.get(Transaction, trans_id)
    if not transaction:
        flash('交易不存在')
        return _dashboard_redirect()
    
    owner = get_user_owner()
    if not owner or transaction.trans_owner_id != owner.owner_id:
        flash('无权操作此交易')
        return _dashboard_redirect()
    
    try:
        transaction.trans_status = TransactionStatus(status)
        db.session.commit()
        flash('状态已更新')
    except ValueError:
        flash('无效的状态')
    
    return _dashboard_redirect()


@transactions.route('/batch-verify', methods=['POST'])
@login_required
def batch_verify():
    """批量核对选中的交易"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return _dashboard_redirect()
    
    trans_ids = request.form.getlist('trans_ids', type=int)
    if not trans_ids:
        flash('请选择要核对的交易')
        return _dashboard_redirect()
    
    count = 0
    for trans_id in trans_ids:
        transaction = db.session.get(Transaction, trans_id)
        if transaction and transaction.trans_owner_id == owner.owner_id:
            if transaction.trans_status == TransactionStatus.UNVERIFIED:
                transaction.trans_status = TransactionStatus.VERIFIED
                count += 1
    
    db.session.commit()
    flash(f'已核对 {count} 笔交易')
    return _dashboard_redirect()


@transactions.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete():
    """批量删除选中的交易"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return _dashboard_redirect()

    trans_ids = request.form.getlist('trans_ids', type=int)
    if not trans_ids:
        flash('请选择要删除的交易')
        return _dashboard_redirect()

    affected = {}  # account_id -> earliest_datetime
    transactions_to_delete = []
    count = 0
    for trans_id in trans_ids:
        transaction = db.session.get(Transaction, trans_id)
        if transaction and transaction.trans_owner_id == owner.owner_id:
            acct_id = transaction.trans_account_id
            dt = transaction.trans_datetime
            if acct_id not in affected or dt < affected[acct_id]:
                affected[acct_id] = dt

            if transaction.trans_counter_id:
                counter = db.session.get(Transaction, transaction.trans_counter_id)
                if counter:
                    c_acct = counter.trans_account_id
                    c_dt = counter.trans_datetime
                    if c_acct not in affected or c_dt < affected[c_acct]:
                        affected[c_acct] = c_dt
                    counter.trans_counter_id = None
                    transactions_to_delete.append(counter)

            transaction.trans_counter_id = None
            transactions_to_delete.append(transaction)
            count += 1

    db.session.flush()

    for t in transactions_to_delete:
        db.session.delete(t)

    for acct_id, dt in affected.items():
        invalidate_account_balances(acct_id, dt)

    db.session.commit()
    flash(f'已删除 {count} 笔交易')
    return _dashboard_redirect()


@transactions.route('/edit/<int:trans_id>', methods=['POST'])
@login_required
def edit_transaction(trans_id):
    """编辑交易"""
    transaction = db.session.get(Transaction, trans_id)
    if not transaction:
        flash('交易不存在')
        return _dashboard_redirect()

    owner = get_user_owner()
    if not owner or transaction.trans_owner_id != owner.owner_id:
        flash('无权编辑此交易')
        return _dashboard_redirect()

    category_id = request.form.get('category_id', type=int)
    description = request.form.get('description', '')
    trans_date = request.form.get('trans_date', '')
    trans_time = request.form.get('trans_time', '00:00')

    if not category_id:
        flash('请填写完整信息')
        return _dashboard_redirect()

    is_pair = transaction.trans_counter_id is not None

    old_account_id = transaction.trans_account_id
    old_datetime = transaction.trans_datetime
    old_counter_account_id = None
    old_counter_datetime = None
    txn_new_account_id = None
    counter_new_account_id = None

    if not is_pair:
        amount = request.form.get('amount', type=float)
        account_id = request.form.get('account_id', type=int)
        if not account_id or not amount:
            flash('请填写完整信息')
            return _dashboard_redirect()

        currency = request.form.get('currency', transaction.trans_currency_name)
        has_fx = transaction.trans_fx_currency_name is not None
        fx_rate_provided = request.form.get('fx_rate') is not None

        sign = 1 if transaction.trans_amount > 0 else -1
        hkd_amount = amount

        if has_fx:
            fx_currency = transaction.trans_fx_currency_name or currency
            stored_fx_rate = transaction.trans_fx_rate or 0.0
            if fx_rate_provided:
                fx_rate_input = request.form.get('fx_rate', type=float) or 0.0
                spot_rate = get_fx_rate_to_hkd(fx_currency, transaction.trans_datetime.date())
                inv_spot_rate = 1.0 / spot_rate
                effective_rate = fx_rate_input if fx_rate_input > 0 else inv_spot_rate
                stored_rate = fx_rate_input if fx_rate_input > 0 else 0.0
                hkd_amount = round(amount / effective_rate, 2)
                transaction.trans_fx_rate = stored_rate
            elif stored_fx_rate > 0:
                hkd_amount = round(amount / stored_fx_rate, 2)
            else:
                spot_rate = get_fx_rate_to_hkd(fx_currency, transaction.trans_datetime.date())
                hkd_amount = round(amount / (1.0 / spot_rate), 2)
            transaction.trans_fx_amount = sign * amount
            transaction.trans_fx_currency_name = fx_currency
            transaction.trans_is_rhs_currency_ind = True
        elif fx_rate_provided and currency != 'HKD':
            fx_rate_input = request.form.get('fx_rate', type=float) or 0.0
            fx_auto = request.form.get('fx_auto', '0') == '1'
            spot_rate = get_fx_rate_to_hkd(currency, transaction.trans_datetime.date())
            inv_spot_rate = 1.0 / spot_rate
            effective_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else inv_spot_rate
            stored_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else 0.0
            hkd_amount = round(amount / effective_rate, 2)
            transaction.trans_currency_name = 'HKD'
            transaction.trans_fx_amount = sign * amount
            transaction.trans_fx_rate = stored_rate
            transaction.trans_fx_currency_name = currency
            transaction.trans_is_rhs_currency_ind = True
        elif not has_fx:
            transaction.trans_currency_name = currency
        else:
            transaction.trans_currency_name = currency
            transaction.trans_fx_amount = None
            transaction.trans_fx_rate = None
            transaction.trans_fx_currency_name = None
            transaction.trans_is_rhs_currency_ind = None

        transaction.trans_amount = sign * hkd_amount
        transaction.trans_account_id = account_id
        transaction.trans_category_id = category_id
        transaction.trans_desc = description
        txn_new_account_id = account_id

        account = db.session.get(Account, account_id)
        if account and not has_fx:
            unit_submitted = 'unit' in request.form or 'unit_price' in request.form
            if unit_submitted:
                unit = request.form.get('unit', type=float)
                unit_price = request.form.get('unit_price', type=float)
                has_unit_concept = account.account_has_unit_ind
                edit_show_units = has_unit_concept or currency != 'HKD'
                if edit_show_units:
                    has_amt = True
                    has_unit = unit is not None
                    has_up = unit_price is not None
                    if has_unit and has_up:
                        if has_unit_concept:
                            # 有单位概念账户（如基金）：单位×单价 = 账户默认货币金额（非 HKD 账户的金额为 HKD 折算值，不做强制校验）
                            amount_from_units = round(unit * unit_price, 2)
                            if account.account_currency_name == 'HKD' and abs(amount - amount_from_units) > 0.02:
                                flash(f'单位×单价 ({unit} × {unit_price} ≈ {amount_from_units}) 与金额 ({amount}) 不符')
                                return _dashboard_redirect()
                        else:
                            hkd_from_units = round(unit * unit_price, 2)
                            if has_amt and unit_price > 0:
                                if abs(abs(hkd_amount) - hkd_from_units) > 0.02:
                                    flash(f'单位×单价 ({unit} × {unit_price} ≈ {hkd_from_units}) 与交易金额 ({abs(hkd_amount)}) 不符')
                                    return _dashboard_redirect()
                            else:
                                hkd_amount = sign * hkd_from_units
                                transaction.trans_amount = hkd_amount
                    elif has_unit and has_amt:
                        unit_price = round((amount if has_unit_concept else abs(hkd_amount)) / unit, 6)
                    elif has_up and has_amt:
                        unit = round((amount if has_unit_concept else abs(hkd_amount)) / unit_price, 6)
                    if unit is not None and unit_price is not None:
                        transaction.trans_unit = unit if sign > 0 else -unit
                        transaction.trans_unit_price = unit_price
                        transaction.trans_unit_name = None
                        transaction.trans_is_rhs_currency_ind = None
                    else:
                        transaction.trans_unit = None
                        transaction.trans_unit_price = None
                        transaction.trans_unit_name = None
                        transaction.trans_is_rhs_currency_ind = None
                else:
                    transaction.trans_unit = None
                    transaction.trans_unit_price = None
                    transaction.trans_unit_name = None
                    transaction.trans_is_rhs_currency_ind = None

        counter = None
    else:
        out_account_id = request.form.get('out_account_id', type=int)
        out_amount = request.form.get('out_amount', type=float)
        in_account_id = request.form.get('in_account_id', type=int)
        in_amount = request.form.get('in_amount', type=float)
        if not out_account_id or not in_account_id or not out_amount or not in_amount:
            flash('请填写完整信息')
            return _dashboard_redirect()
        if out_amount <= 0 or in_amount <= 0:
            flash('金额必须大于 0')
            return _dashboard_redirect()

        counter = db.session.get(Transaction, transaction.trans_counter_id)
        if counter:
            old_counter_account_id = counter.trans_account_id
            old_counter_datetime = counter.trans_datetime

        # 区分转出/转入两侧（转出为负金额，转入为正金额）
        if transaction.trans_amount < 0:
            out_txn, in_txn = transaction, counter
            txn_new_account_id, counter_new_account_id = out_account_id, in_account_id
        else:
            in_txn, out_txn = transaction, counter
            txn_new_account_id, counter_new_account_id = in_account_id, out_account_id

        out_account = db.session.get(Account, out_account_id)
        in_account = db.session.get(Account, in_account_id)

        if out_txn:
            out_txn.trans_account_id = out_account_id
            out_txn.trans_amount = -round(out_amount, 2)
            unit_err = _apply_side_units(out_txn, out_account, out_amount, 'out')
            if unit_err:
                flash(unit_err)
                return _dashboard_redirect()
        if in_txn:
            in_txn.trans_account_id = in_account_id
            in_txn.trans_amount = round(in_amount, 2)
            unit_err = _apply_side_units(in_txn, in_account, in_amount, 'in')
            if unit_err:
                flash(unit_err)
                return _dashboard_redirect()

        transaction.trans_category_id = category_id
        transaction.trans_desc = description
        if counter:
            counter.trans_category_id = category_id
            counter.trans_desc = description

    new_datetime = old_datetime
    try:
        new_datetime = datetime.strptime(
            f'{trans_date} {trans_time}', '%Y-%m-%d %H:%M'
        ).replace(tzinfo=timezone.utc)
        transaction.trans_datetime = new_datetime
        if is_pair and counter:
            counter.trans_datetime = new_datetime
    except ValueError:
        pass
    
    earliest_dt = old_datetime if _ensure_utc(old_datetime) < _ensure_utc(new_datetime) else new_datetime
    
    # 余额缓存失效
    invalidate_account_balances(old_account_id, earliest_dt)
    if txn_new_account_id and txn_new_account_id != old_account_id:
        invalidate_account_balances(txn_new_account_id, earliest_dt)
    if is_pair and counter:
        invalidate_account_balances(counter_new_account_id, earliest_dt)
        if old_counter_account_id:
            invalidate_account_balances(old_counter_account_id, earliest_dt)
    
    db.session.commit()
    flash('交易更新成功')
    return _dashboard_redirect()
