from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app import db
from app.models import Transaction, Account, Category, Owner, TransactionStatus, AccountBalance
from app.routes.accounts import get_fx_rate_to_hkd

transactions = Blueprint('transactions', __name__)


def invalidate_account_balances(account_id, from_datetime):
    """删除指定账户从指定日期起的所有缓存日终余额记录"""
    if not account_id:
        return
    AccountBalance.query.filter(
        AccountBalance.account_id == account_id,
        AccountBalance.as_of_dt >= from_datetime.date()
    ).delete(synchronize_session=False)


def _ensure_utc(dt):
    """确保datetime带UTC时区信息，用于安全比较"""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def get_user_owner():
    """获取当前用户的Owner"""
    if current_user.owner:
        return current_user.owner
    return None


def get_visible_transactions_query(start_date=None, end_date=None, status_filter=None, 
                                   category_id=None, account_id=None):
    """获取当前用户可见的交易查询，支持按状态、分类、账户筛选"""
    owner = get_user_owner()
    if not owner:
        return Transaction.query.filter(False)
    
    query = Transaction.query
    
    if current_user.can_view_family_data():
        family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
        query = query.filter(Transaction.trans_owner_id.in_(family_owner_ids))
    else:
        query = query.filter_by(trans_owner_id=owner.owner_id)
    
    if start_date:
        query = query.filter(Transaction.trans_datetime >= start_date)
    if end_date:
        query = query.filter(Transaction.trans_datetime <= end_date)
    
    if status_filter:
        query = query.filter_by(trans_status=TransactionStatus(status_filter))
    
    if category_id:
        query = query.filter_by(trans_category_id=category_id)
    
    if account_id:
        query = query.filter_by(trans_account_id=account_id)
    
    return query.order_by(Transaction.trans_datetime.desc())


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
    params = {'tab': 'list-tab'}
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
    
    transactions_list = get_visible_transactions_query(
        start, end, status_filter, category_id, account_id
    ).all()
    
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
    
    accounts = Account.query.filter_by(account_owner_id=owner.owner_id)\
        .order_by(Account.account_type, Account.account_custodian, 
                  Account.account_owner_id, Account.account_name).all()
    
    categories = Category.query.order_by(
        Category.category_class, Category.category_subclass, Category.category_name
    ).all()
    
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

    fx_rate_input = None
    fx_auto = False
    is_fx = (currency != 'HKD' and trans_type != 'transfer')

    if is_fx:
        fx_rate_input = request.form.get('fx_rate', type=float)
        fx_auto = request.form.get('fx_auto', '0') == '1'
        if fx_rate_input is None:
            fx_rate_input = 0.0

        spot_rate = get_fx_rate_to_hkd(currency, trans_datetime.date())
        inv_spot_rate = 1.0 / spot_rate
        effective_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else inv_spot_rate
        stored_fx_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else 0.0
        hkd_amount = round(amount / effective_rate, 2)
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
        if is_fx:
            kwargs.update({
                'trans_fx_currency_name': currency,
                'trans_fx_amount': amount,
                'trans_fx_rate': stored_fx_rate,
            })
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
        if is_fx:
            kwargs.update({
                'trans_fx_currency_name': currency,
                'trans_fx_amount': -amount,
                'trans_fx_rate': stored_fx_rate,
            })
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
        if is_fx:
            kwargs.update({
                'trans_fx_currency_name': currency,
                'trans_fx_amount': amount,
                'trans_fx_rate': stored_fx_rate,
            })
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

    amount = request.form.get('amount', type=float)
    category_id = request.form.get('category_id', type=int)
    account_id = request.form.get('account_id', type=int)
    description = request.form.get('description', '')
    trans_date = request.form.get('trans_date', '')
    trans_time = request.form.get('trans_time', '00:00')

    if not account_id or not category_id or not amount:
        flash('请填写完整信息')
        return _dashboard_redirect()

    is_pair = transaction.trans_counter_id is not None

    old_account_id = transaction.trans_account_id
    old_datetime = transaction.trans_datetime
    old_counter_account_id = None
    old_counter_datetime = None

    currency = request.form.get('currency', transaction.trans_currency_name)
    has_fx = transaction.trans_fx_currency_name is not None
    fx_rate_provided = request.form.get('fx_rate') is not None

    if not is_pair:
        sign = 1 if transaction.trans_amount > 0 else -1
        hkd_amount = amount

        if has_fx:
            if fx_rate_provided:
                fx_rate_input = request.form.get('fx_rate', type=float) or 0.0
                spot_rate = get_fx_rate_to_hkd(transaction.trans_fx_currency_name, transaction.trans_datetime.date())
                inv_spot_rate = 1.0 / spot_rate
                effective_rate = fx_rate_input if fx_rate_input > 0 else inv_spot_rate
                stored_rate = fx_rate_input if fx_rate_input > 0 else 0.0
                hkd_amount = round(amount / effective_rate, 2)
                transaction.trans_fx_rate = stored_rate
            elif (transaction.trans_fx_rate or 0) > 0:
                hkd_amount = round(amount / transaction.trans_fx_rate, 2)
            else:
                spot_rate = get_fx_rate_to_hkd(transaction.trans_fx_currency_name, transaction.trans_datetime.date())
                hkd_amount = round(amount / (1.0 / spot_rate), 2)
            transaction.trans_fx_amount = sign * amount
        elif fx_rate_provided and currency != 'HKD':
            fx_rate_input = request.form.get('fx_rate', type=float) or 0.0
            fx_auto = request.form.get('fx_auto', '0') == '1'
            spot_rate = get_fx_rate_to_hkd(currency, transaction.trans_datetime.date())
            inv_spot_rate = 1.0 / spot_rate
            effective_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else inv_spot_rate
            stored_rate = fx_rate_input if (fx_rate_input > 0 and not fx_auto) else 0.0
            hkd_amount = round(amount / effective_rate, 2)
            transaction.trans_fx_currency_name = currency
            transaction.trans_fx_amount = sign * amount
            transaction.trans_fx_rate = stored_rate
            transaction.trans_currency_name = 'HKD'
        elif not has_fx:
            transaction.trans_currency_name = currency
        else:
            transaction.trans_fx_currency_name = None
            transaction.trans_fx_amount = None
            transaction.trans_fx_rate = None
            transaction.trans_currency_name = currency

        transaction.trans_amount = sign * hkd_amount
        transaction.trans_account_id = account_id
        transaction.trans_category_id = category_id
        transaction.trans_desc = description
        counter = None
    else:
        counter = db.session.get(Transaction, transaction.trans_counter_id)
        if counter:
            old_counter_account_id = counter.trans_account_id
            old_counter_datetime = counter.trans_datetime
        if transaction.trans_amount < 0:
            transaction.trans_amount = -amount
            if counter:
                counter.trans_amount = amount
                counter.trans_account_id = account_id
        else:
            transaction.trans_amount = amount
            if counter:
                counter.trans_amount = -amount
                counter.trans_account_id = account_id
        
        transaction.trans_account_id = account_id
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
    
    invalidate_account_balances(old_account_id, earliest_dt)
    if account_id != old_account_id:
        invalidate_account_balances(account_id, earliest_dt)
    
    if is_pair and counter:
        if old_counter_account_id:
            invalidate_account_balances(old_counter_account_id, earliest_dt)
            if counter.trans_account_id != old_counter_account_id:
                invalidate_account_balances(counter.trans_account_id, earliest_dt)
        else:
            invalidate_account_balances(counter.trans_account_id, earliest_dt)
    
    db.session.commit()
    flash('交易更新成功')
    return _dashboard_redirect()