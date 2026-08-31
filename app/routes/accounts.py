import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import cast
from urllib.request import urlopen, Request
from urllib.error import URLError

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import CursorResult, nullsfirst, case, func, select, delete, update, or_
from app import db
from app.models import (Account, AccountType, Owner, BluecoinsAccountMapping,
                        Transaction, TransactionStatus, AccountBalance, CurrencyConversion)

accounts = Blueprint('accounts', __name__)


def get_user_owner():
    """获取当前用户的Owner"""
    if current_user.owner:
        return current_user.owner
    return None


def get_family_members():
    """获取当前用户家庭的所有成员"""
    owner = get_user_owner()
    if not owner:
        return []
    stmt = select(Owner).where(Owner.family_id == owner.family_id)
    return db.session.execute(stmt).scalars().all()


def get_account_eod_balance(account_id, as_of_date):
    """获取指定账户在指定日期的日终余额，若无缓存则从交易记录计算并存储"""
    eod = as_of_date
    # 查询缓存余额
    stmt = select(AccountBalance).where(
        AccountBalance.account_id == account_id,
        AccountBalance.as_of_dt == eod
    )
    record = db.session.execute(stmt).scalars().first()
    if record:
        return record.account_balance

    day_end = datetime(eod.year, eod.month, eod.day, 23, 59, 59)
    # 计算截止日终的交易总金额
    raw_stmt = select(func.coalesce(func.sum(Transaction.trans_amount), 0.0)).where(
        Transaction.trans_account_id == account_id,
        Transaction.trans_datetime <= day_end
    )
    raw_balance = db.session.scalar(raw_stmt) or 0.0

    account = db.session.get(Account, account_id)
    if account and account.account_type.is_liability:
        raw_balance = -raw_balance

    fx_balance = 0.0
    fx_cost_numerator = 0.0
    fx_cost_denominator = 0.0
    deposit_units = 0.0
    has_fx = False

    if account and account.account_currency_name != 'HKD':
        # 获取外币账户的单位交易（外汇用 trans_fx_*，投资单位用 trans_unit_*）
        fx_stmt = select(Transaction).where(
            Transaction.trans_account_id == account_id,
            Transaction.trans_datetime <= day_end,
            or_(Transaction.trans_fx_currency_name.isnot(None), Transaction.trans_unit.isnot(None))
        )
        fx_transactions = db.session.execute(fx_stmt).scalars().all()

        for t in fx_transactions:
            has_fx = True
            if t.is_fx:
                # 外汇：trans_fx_amount=外汇金额，trans_fx_rate=汇率
                fx_amt = t.trans_fx_amount or 0.0
                fx_rate = t.trans_fx_rate or 0.0
                fx_balance += fx_amt
                if fx_rate > 0:
                    fx_cost_numerator += fx_amt / fx_rate
                    fx_cost_denominator += fx_amt
                    deposit_units += fx_amt
            else:
                # 投资单位（外币基金）：trans_unit=份额，trans_unit_price=账户货币单价
                shares = t.trans_unit or 0.0
                price = t.trans_unit_price or 0.0
                fx_balance += shares * price
                deposit_units += shares
                if price > 0 and shares != 0:
                    fx_cost_numerator += t.trans_amount or 0.0
                    fx_cost_denominator += shares

    fx_cost_rate = (fx_cost_numerator / fx_cost_denominator) if fx_cost_denominator != 0 else None
    acct_fx_currency = account.account_currency_name if (has_fx and account) else None
    acct_fx_amount = fx_balance if has_fx else None
    acct_deposit_unit = deposit_units if deposit_units != 0 else None

    balance_record = AccountBalance(
        as_of_dt=eod,
        account_id=account_id,
        account_balance=raw_balance,
        deposit_unit=acct_deposit_unit,
        account_fx_currency_name=acct_fx_currency,
        account_fx_amount=acct_fx_amount,
        account_unit_cost_rate=fx_cost_rate,
    )
    db.session.add(balance_record)
    db.session.commit()

    return raw_balance


def get_fx_rate_to_hkd(currency_code, target_date):
    """获取指定货币在指定日期的HKD汇率，优先从缓存读取，否则从 frankfurter.app API 获取并缓存"""
    if currency_code == 'HKD':
        return 1.0

    stmt = select(CurrencyConversion).where(
        CurrencyConversion.currency_name_lhs == currency_code,
        CurrencyConversion.currency_name_rhs == 'HKD',
        CurrencyConversion.currency_conversion_date == target_date
    )
    existing = db.session.execute(stmt).scalars().first()
    if existing:
        return existing.currency_conversion_rate

    date_str = target_date.strftime('%Y-%m-%d')
    url = f'https://api.frankfurter.app/{date_str}?from={currency_code}&to=HKD'

    try:
        req = Request(url, headers={'User-Agent': 'DeepSeekLedger/1.0'})
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            rate = data['rates']['HKD']
    except (URLError, KeyError, json.JSONDecodeError, ValueError):
        return 1.0

    record = CurrencyConversion(
        currency_name_lhs=currency_code,
        currency_name_rhs='HKD',
        currency_conversion_rate=rate,
        currency_conversion_date=target_date,
    )
    db.session.add(record)
    db.session.commit()
    return rate


@accounts.route('/accounts/fx_rate')
@login_required
def fx_rate():
    """AJAX 获取指定货币在指定日期的 HKD 汇率"""
    currency = request.args.get('currency', 'HKD')
    date_str = request.args.get('date', '')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = datetime.now(timezone.utc).date()
    rate = get_fx_rate_to_hkd(currency, target_date)
    return jsonify({'rate': rate, 'currency': currency, 'date': target_date.strftime('%Y-%m-%d')})


def _get_accounts_balance_status(account_ids, as_of_date):
    """批量获取多个账户截至指定日期的交易核对状态汇总。"""
    if not account_ids:
        return {}

    stmt = (
        select(
            Transaction.trans_account_id,
            Transaction.trans_status,
            func.count(Transaction.trans_id)
        )
        .where(
            Transaction.trans_account_id.in_(account_ids),
            func.date(Transaction.trans_datetime) <= as_of_date
        )
        .group_by(Transaction.trans_account_id, Transaction.trans_status)
    )
    results = db.session.execute(stmt).all()

    status_by_account = {}
    for acct_id, status, count in results:
        status_by_account.setdefault(acct_id, {})[status] = count

    final_status = {}
    for acct_id in account_ids:
        counts = status_by_account.get(acct_id, {})
        if counts.get(TransactionStatus.FLAGGED, 0) > 0:
            final_status[acct_id] = 'FLAGGED'
        elif counts.get(TransactionStatus.UNVERIFIED, 0) > 0:
            final_status[acct_id] = 'UNVERIFIED'
        else:
            final_status[acct_id] = 'VERIFIED'
    return final_status


def compute_balance_sheet(accounts_list, start_date, end_date):
    """计算资产负债表，非HKD账户按期初/期末各自日期的汇率折算为HKD"""
    day_before_start = start_date - timedelta(days=1)

    account_ids = [a.account_id for a in accounts_list]
    start_statuses = _get_accounts_balance_status(account_ids, day_before_start)
    end_statuses = _get_accounts_balance_status(account_ids, end_date)

    assets = []
    liabilities = []
    total_asset_start = 0.0
    total_asset_end = 0.0
    total_liability_start = 0.0
    total_liability_end = 0.0

    for account in accounts_list:
        balance_start = get_account_eod_balance(account.account_id, day_before_start)
        balance_end = get_account_eod_balance(account.account_id, end_date)

        currency = account.account_currency_name

        # 查询日终余额记录（可能含外币信息）
        stmt_start = select(AccountBalance).where(
            AccountBalance.account_id == account.account_id,
            AccountBalance.as_of_dt == day_before_start
        )
        balance_start_record = db.session.execute(stmt_start).scalars().first()

        stmt_end = select(AccountBalance).where(
            AccountBalance.account_id == account.account_id,
            AccountBalance.as_of_dt == end_date
        )
        balance_end_record = db.session.execute(stmt_end).scalars().first()

        if balance_end_record and balance_end_record.account_fx_currency_name:
            hkd_start = round(balance_start, 2)
            hkd_end = round(balance_end, 2)
        else:
            fx_start = 1.0 / get_fx_rate_to_hkd(currency, day_before_start)
            fx_end = 1.0 / get_fx_rate_to_hkd(currency, end_date)
            hkd_start = round(balance_start / fx_start, 2)
            hkd_end = round(balance_end / fx_end, 2)

        hkd_change = round(hkd_end - hkd_start, 2)

        item = {
            'id': account.account_id,
            'name': account.account_name,
            'custodian': account.account_custodian,
            'type': account.account_type.value,
            'currency': currency,
            'owner': account.owner.owner_name,
            'balance_start': hkd_start,
            'balance_end': hkd_end,
            'change': hkd_change,
            'is_closed': account.account_close_date is not None,
            'has_unit': account.account_has_unit_ind,
            'other_name': account.account_other_name,
            'owner_id': account.account_owner_id,
            'create_date': account.account_create_date.strftime('%Y-%m-%d') if account.account_create_date else '',
            'close_date': account.account_close_date.strftime('%Y-%m-%d') if account.account_close_date else '',
            'isin': account.account_isin,
            '_raw_start': balance_start,
            '_raw_end': balance_end,
            '_has_fx_start': bool(balance_start_record and balance_start_record.account_fx_currency_name),
            '_account_fx_amount_start': balance_start_record.account_fx_amount if balance_start_record else None,
            '_deposit_unit_start': balance_start_record.deposit_unit if balance_start_record else None,
            '_account_fx_cost_rate_start': balance_start_record.account_unit_cost_rate if balance_start_record else None,
            '_has_fx_end': bool(balance_end_record and balance_end_record.account_fx_currency_name),
            '_account_fx_amount_end': balance_end_record.account_fx_amount if balance_end_record else None,
            '_deposit_unit_end': balance_end_record.deposit_unit if balance_end_record else None,
            '_account_fx_cost_rate_end': balance_end_record.account_unit_cost_rate if balance_end_record else None,
            'balance_start_status': start_statuses.get(account.account_id),
            'balance_end_status': end_statuses.get(account.account_id),
        }

        if account.account_type.is_liability:
            liabilities.append(item)
            total_liability_start += hkd_start
            total_liability_end += hkd_end
        else:
            assets.append(item)
            total_asset_start += hkd_start
            total_asset_end += hkd_end

    assets.sort(key=lambda x: (x['type'], x['owner'], x['custodian']))
    liabilities.sort(key=lambda x: (x['type'], x['owner'], x['custodian']))

    return {
        'assets': assets,
        'liabilities': liabilities,
        'total_asset_start': total_asset_start,
        'total_asset_end': total_asset_end,
        'total_liability_start': total_liability_start,
        'total_liability_end': total_liability_end,
        'net_worth_start': round(total_asset_start - total_liability_start, 2),
        'net_worth_end': round(total_asset_end - total_liability_end, 2),
        'net_worth_change': round(
            (total_asset_end - total_liability_end) - (total_asset_start - total_liability_start), 2
        ),
    }


@accounts.route('/accounts')
@login_required
def list_accounts():
    """账户概览"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('transactions.dashboard'))

    type_order = case(
        (Account.account_type == 'CASH', 1),
        (Account.account_type == 'SAVING', 2),
        (Account.account_type == 'TIME_DEPOSIT', 3),
        (Account.account_type == 'CURRENCY_LINKED_DEPOSIT', 4),
        (Account.account_type == 'FUND', 5),
        (Account.account_type == 'INVESTMENT', 6),
        (Account.account_type == 'MPF', 7),
        (Account.account_type == 'CREDIT_CARD', 8),
        (Account.account_type == 'MORTGAGE', 9),
        else_=10
    )

    if current_user.can_view_family_data():
        # 获取家庭成员的所有 owner_id
        family_owner_stmt = select(Owner).where(Owner.family_id == owner.family_id)
        family_owners = db.session.execute(family_owner_stmt).scalars().all()
        family_owner_ids = [o.owner_id for o in family_owners]

        stmt = (
            select(Account)
            .where(Account.account_owner_id.in_(family_owner_ids))
            .order_by(
                nullsfirst(Account.account_close_date),
                type_order,
                Account.account_owner_id,
                Account.account_custodian,
                Account.account_currency_name,
                Account.account_name,
                Account.account_other_name
            )
        )
    else:
        stmt = (
            select(Account)
            .where(Account.account_owner_id == owner.owner_id)
            .order_by(
                nullsfirst(Account.account_close_date),
                type_order,
                Account.account_owner_id,
                Account.account_custodian,
                Account.account_currency_name,
                Account.account_name,
                Account.account_other_name
            )
        )

    accounts_list = db.session.execute(stmt).scalars().all()
    members = get_family_members()

    total = len(accounts_list)
    active = sum(1 for a in accounts_list if not a.account_close_date)
    closed = total - active

    type_breakdown = defaultdict(int)
    currency_breakdown = defaultdict(int)
    owner_breakdown = defaultdict(int)
    for a in accounts_list:
        type_breakdown[a.account_type.value] += 1
        currency_breakdown[a.account_currency_name] += 1
        owner_breakdown[a.owner.owner_name] += 1

    # 资产负债表数据：显示与所选时间范围有重合的账户（含已关闭但期间内处于开启状态的账户）
    today = datetime.now(timezone.utc).date()
    first_of_month = today.replace(day=1)
    start_str = request.args.get('start_date', '') or session.get('accts_start_date', '')
    end_str = request.args.get('end_date', '') or session.get('accts_end_date', '')
    if start_str or end_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else first_of_month
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
            if end_date < start_date:
                start_date, end_date = end_date, start_date
        except ValueError:
            start_date = first_of_month
            end_date = today
    else:
        start_date = first_of_month
        end_date = today
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

    balance_sheet_accounts_list = [
        a for a in accounts_list
        if (not a.account_create_date or a.account_create_date <= end_date)
        and (not a.account_close_date or a.account_close_date >= start_date)
    ]
    balance_sheet = compute_balance_sheet(balance_sheet_accounts_list, start_date, end_date)

    # Persist dates to session for cross-page navigation
    session['accts_start_date'] = start_date.strftime('%Y-%m-%d')
    session['accts_end_date'] = end_date.strftime('%Y-%m-%d')

    active_tab = request.args.get('tab', 'finance')

    return render_template(
        'accounts.html',
        accounts=accounts_list,
        account_types=AccountType,
        members=members,
        current_owner=owner,
        total_accounts=total,
        active_accounts=active,
        closed_accounts=closed,
        type_breakdown=dict(type_breakdown),
        currency_breakdown=dict(currency_breakdown),
        owner_breakdown=dict(owner_breakdown),
        balance_sheet=balance_sheet,
        start_date=start_str,
        end_date=end_str,
        active_tab=active_tab,
    )


@accounts.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
    """添加账户"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('accounts.list_accounts'))

    account_name = request.form.get('account_name', '').strip()
    account_type = request.form.get('account_type', 'SAVING')
    account_custodian = request.form.get('account_custodian', '').strip()
    account_other_name = request.form.get('account_other_name', '').strip()
    currency = request.form.get('currency', 'HKD')
    create_date_str = request.form.get('account_create_date', '')
    close_date_str = request.form.get('account_close_date', '')

    # 确定账户拥有者
    owner_id = request.form.get('account_owner_id', type=int)
    if not owner_id or not current_user.is_adult():
        owner_id = owner.owner_id
    else:
        target_owner = db.session.get(Owner, owner_id)
        if not target_owner or target_owner.family_id != owner.family_id:
            owner_id = owner.owner_id

    # 验证必填字段
    if not account_name:
        flash('请填写账户名称')
        return redirect(url_for('accounts.list_accounts'))
    if not account_custodian:
        flash('请填写机构/钱包')
        return redirect(url_for('accounts.list_accounts'))

    # 解析日期
    try:
        create_date = datetime.strptime(create_date_str, '%Y-%m-%d').date() if create_date_str else datetime.now(timezone.utc).date()
    except ValueError:
        create_date = datetime.now(timezone.utc).date()

    close_date = None
    if close_date_str:
        try:
            close_date = datetime.strptime(close_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('关闭日期格式无效')
            return redirect(url_for('accounts.list_accounts'))

    # 创建账户
    has_unit_ind = (request.form.get('account_has_unit_ind', '0') == '1') or account_type == 'FUND'
    account_isin = (request.form.get('account_isin', '') or '').strip().upper() or None
    account = Account(
        account_name=account_name,
        account_other_name=account_other_name if account_other_name else None,
        account_type=AccountType[account_type],
        account_create_date=create_date,
        account_close_date=close_date,
        account_custodian=account_custodian,
        account_currency_name=currency,
        account_owner_id=owner_id,
        account_has_unit_ind=has_unit_ind,
        account_isin=account_isin
    )
    db.session.add(account)
    db.session.commit()
    flash('账户添加成功')
    return redirect(url_for('accounts.list_accounts', tab='accounts'))


@accounts.route('/accounts/<int:account_id>/edit', methods=['POST'])
@login_required
def edit_account(account_id):
    """编辑账户"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('auth.login'))

    account = db.session.get(Account, account_id)
    if not account:
        flash('账户不存在')
        return redirect(url_for('accounts.list_accounts'))

    # 权限检查
    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        flash('无权修改此账户')
        return redirect(url_for('accounts.list_accounts'))

    account.account_name = request.form.get('account_name', account.account_name).strip()
    account.account_other_name = request.form.get('account_other_name', '').strip() or None
    account.account_custodian = request.form.get('account_custodian', account.account_custodian).strip()
    account.account_currency_name = request.form.get('account_currency_name', account.account_currency_name)
    account.account_has_unit_ind = request.form.get('account_has_unit_ind', '0') == '1'
    account.account_isin = (request.form.get('account_isin', '') or '').strip().upper() or None

    # 更新创建日期
    create_date_str = request.form.get('account_create_date', '')
    if create_date_str:
        try:
            account.account_create_date = datetime.strptime(create_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # 更新关闭日期
    close_date_str = request.form.get('account_close_date', '')
    if close_date_str:
        try:
            account.account_close_date = datetime.strptime(close_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        account.account_close_date = None

    # 更新拥有者（仅成人可操作）
    if current_user.is_adult():
        new_owner_id = request.form.get('account_owner_id', type=int)
        if new_owner_id:
            target_owner = db.session.get(Owner, new_owner_id)
            if target_owner and target_owner.family_id == owner.family_id:
                account.account_owner_id = new_owner_id

    db.session.commit()
    flash('账户更新成功')
    target_tab = request.form.get('tab', 'accounts')
    if target_tab not in ('finance', 'accounts'):
        target_tab = 'accounts'
    return redirect(url_for('accounts.list_accounts', tab=target_tab))


@accounts.route('/accounts/<int:account_id>/check-delete')
@login_required
def check_delete_account(account_id):
    """检查账户关联交易（AJAX），返回删除确认弹窗 HTML"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('auth.login'))
    
    account = db.session.get(Account, account_id)
    if not account:
        return '<p style="color: #e74c3c; text-align: center;">账户不存在</p>'

    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        return '<p style="color: #e74c3c; text-align: center;">无权删除此账户</p>'

    # 关联交易计数
    count_stmt = select(func.count()).select_from(Transaction).where(
        Transaction.trans_account_id == account_id
    )
    transaction_count = db.session.scalar(count_stmt)
    csrf_token = generate_csrf()

    if transaction_count == 0:
        return f'''<div id="delete-content-data">
            <p style="text-align: center; margin-bottom: 16px;">该账户没有关联交易，可以安全删除。</p>
            <form method="POST" action="{url_for('accounts.confirm_delete_account', account_id=account_id)}">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <input type="hidden" name="action" value="delete">
                <div style="display: flex; gap: 12px; justify-content: center;">
                    <button type="submit" class="btn btn-danger">确认删除</button>
                    <button type="button" class="btn btn-secondary" onclick="closeDeleteModal()">取消</button>
                </div>
            </form>
        </div>'''

    # 获取家庭成员的所有 owner_id
    family_owner_stmt = select(Owner).where(Owner.family_id == owner.family_id)
    family_owners = db.session.execute(family_owner_stmt).scalars().all()
    family_owner_ids = [o.owner_id for o in family_owners]

    # 目标账户列表（排除自身）
    target_stmt = (
        select(Account)
        .where(
            Account.account_owner_id.in_(family_owner_ids),
            Account.account_id != account_id
        )
        .order_by(Account.account_type, Account.account_custodian, Account.account_name)
    )
    target_accounts = db.session.execute(target_stmt).scalars().all()

    html = f'''<div id="delete-content-data">
    <p style="margin-bottom: 12px;">账户 <strong>"{account.account_name}"</strong> 有 <strong>{transaction_count}</strong> 笔关联交易。</p>
    <p style="color: #888; font-size: 13px; margin-bottom: 16px;">请选择如何处理这些交易：</p>
    
    <form method="POST" action="{url_for('accounts.confirm_delete_account', account_id=account_id)}">
        <input type="hidden" name="csrf_token" value="{csrf_token}">
        
        <div class="form-group" style="padding: 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 12px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="radio" name="action" value="delete" checked onchange="toggleAccountTargetSelect()">
                <span>🗑 <strong>删除所有关联交易</strong>（不可恢复）</span>
            </label>
        </div>
        
        <div class="form-group" style="padding: 12px; background: #f8f9fa; border-radius: 6px; margin-bottom: 16px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="radio" name="action" value="migrate" onchange="toggleAccountTargetSelect()">
                <span>📦 <strong>迁移到另一个账户</strong></span>
            </label>
            <select name="target_account_id" id="target-account-select" style="margin-top: 8px; display: none;">
                <option value="">选择目标账户</option>'''

    for acc in target_accounts:
        html += f'<option value="{acc.account_id}">{acc.account_type.value} · {acc.account_custodian} · {acc.owner.owner_name} · {acc.account_name} ({acc.account_currency_name})</option>'

    html += '''</select>
        </div>
        
        <div style="display: flex; gap: 12px;">
            <button type="submit" class="btn btn-danger">⚠ 确认删除</button>
            <button type="button" class="btn btn-secondary" onclick="closeDeleteModal()">取消</button>
        </div>
    </form>
</div>

<script>
    function toggleAccountTargetSelect() {
        const migrateRadio = document.querySelector('input[value="migrate"]');
        const select = document.getElementById("target-account-select");
        select.style.display = migrateRadio.checked ? "block" : "none";
        select.required = migrateRadio.checked;
    }
</script>'''

    return html


@accounts.route('/accounts/<int:account_id>/delete/confirm', methods=['POST'])
@login_required
def confirm_delete_account(account_id):
    """确认删除账户（处理关联交易）"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('auth.login'))
    
    account = db.session.get(Account, account_id)
    if not account:
        flash('账户不存在')
        return redirect(url_for('accounts.list_accounts'))

    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        flash('无权删除此账户')
        return redirect(url_for('accounts.list_accounts'))

    action = request.form.get('action', 'delete')

    if action == 'migrate':
        target_account_id = request.form.get('target_account_id', type=int)
        target_account = db.session.get(Account, target_account_id)
        if not target_account:
            flash('目标账户无效')
            return redirect(url_for('accounts.list_accounts'))

        # 迁移所有关联交易到目标账户
        upd_stmt = (
            update(Transaction)
            .where(Transaction.trans_account_id == account_id)
            .values(trans_account_id=target_account_id)
        )
        result = cast(CursorResult, db.session.execute(upd_stmt))
        count = result.rowcount
        flash(f'已将 {count} 笔交易迁移到 "{target_account.account_name}"')
    else:
        # 删除所有关联交易（含转账配对）
        trans_stmt = select(Transaction).where(Transaction.trans_account_id == account_id)
        transactions = db.session.execute(trans_stmt).scalars().all()
        count = len(transactions)
        for t in transactions:
            if t.trans_counter_id:
                counter = db.session.get(Transaction, t.trans_counter_id)
                if counter:
                    db.session.delete(counter)
            db.session.delete(t)
        flash(f'已删除 {count} 笔关联交易')

    # 删除 Bluecoins 映射
    del_mapping_stmt = delete(BluecoinsAccountMapping).where(
        BluecoinsAccountMapping.account_id == account_id
    )
    db.session.execute(del_mapping_stmt)

    # 删除账户
    db.session.delete(account)
    db.session.commit()
    flash('账户已删除')
    return redirect(url_for('accounts.list_accounts', tab='accounts'))