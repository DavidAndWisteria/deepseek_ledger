from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db
from app.models import (TimeDeposit, DepositStatus, Transaction, Account, Owner)
from app.routes.transactions import get_user_owner, DEPOSIT_ACCOUNT_TYPES

deposits = Blueprint('deposits', __name__)


def _visible_deposit_stmt():
    """返回当前用户可见的定期存款 SELECT 语句"""
    owner = get_user_owner()
    if not owner:
        return select(TimeDeposit).where(False)

    if current_user.can_view_family_data():
        family_owner_ids = db.session.execute(
            select(Owner.owner_id).where(Owner.family_id == owner.family_id)
        ).scalars().all()
        return select(TimeDeposit).join(Account, TimeDeposit.account_id == Account.account_id).where(
            Account.account_owner_id.in_(family_owner_ids)
        )
    return select(TimeDeposit).join(Account, TimeDeposit.account_id == Account.account_id).where(
        Account.account_owner_id == owner.owner_id
    )


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


@deposits.route('/deposits')
@login_required
def list_deposits():
    """定期存款 / 货币联系存款列表"""
    owner = get_user_owner()
    deposit_accounts = []
    if owner:
        account_stmt = (
            select(Account)
            .where(Account.account_owner_id == owner.owner_id)
            .order_by(Account.account_type, Account.account_custodian, Account.account_name)
        )
        deposit_accounts = db.session.execute(account_stmt).scalars().all()
        deposit_accounts = [a for a in deposit_accounts if a.account_type.value in DEPOSIT_ACCOUNT_TYPES]
    stmt = _visible_deposit_stmt().order_by(TimeDeposit.subscription_date.desc(), TimeDeposit.deposit_id.desc())
    deposits_list = db.session.execute(stmt).scalars().all()
    return render_template('deposits.html', deposits=deposits_list, deposit_accounts=deposit_accounts)


def _reopen_open_flow(trans_id, account, currency, amount, subscription_date, msg):
    """校验失败时重开开立存款弹窗（保留已填内容）"""
    flash(msg)
    return redirect(url_for('transactions.dashboard', tab='list-tab', deposit_flow='open',
                            deposit_trans_id=trans_id or '',
                            deposit_account_id=account.account_id if account else '',
                            deposit_account_type=account.account_type.value if account else '',
                            deposit_currency=currency, deposit_amount=amount or '',
                            deposit_date=subscription_date or ''))


@deposits.route('/deposits/create', methods=['POST'])
@login_required
def create_deposit():
    """开立定期存款/货币联系存款（由添加转账交易触发，交易内容已预填；也可在存款页手动开立）"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('deposits.list_deposits'))

    trans_id = request.form.get('trans_id', type=int)
    account_id = request.form.get('account_id', type=int)
    deposit_currency_name = (request.form.get('deposit_currency_name', '') or 'HKD').strip().upper()
    amount = request.form.get('amount', type=float)
    interest_rate = request.form.get('interest_rate', type=float)
    subscription_date = _parse_date(request.form.get('subscription_date', ''))
    maturity_date = _parse_date(request.form.get('maturity_date', ''))

    transaction = db.session.get(Transaction, trans_id) if trans_id else None
    account = db.session.get(Account, account_id) if account_id else None

    if not account:
        flash('无效的账户')
        return redirect(url_for('deposits.list_deposits'))

    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        flash('无权操作此账户')
        return redirect(url_for('deposits.list_deposits'))

    if account.account_type.value not in DEPOSIT_ACCOUNT_TYPES:
        flash('该账户不是定期存款/货币联系存款账户')
        return redirect(url_for('deposits.list_deposits'))

    if not amount or amount <= 0:
        return _reopen_open_flow(trans_id, account, deposit_currency_name, amount, subscription_date, '请填写存款金额')
    if interest_rate is None:
        return _reopen_open_flow(trans_id, account, deposit_currency_name, amount, subscription_date, '请填写年利率')
    if not subscription_date:
        return _reopen_open_flow(trans_id, account, deposit_currency_name, amount, subscription_date, '请填写开立日期')
    if not maturity_date:
        return _reopen_open_flow(trans_id, account, deposit_currency_name, amount, subscription_date, '请填写到期日期')
    if maturity_date <= subscription_date:
        return _reopen_open_flow(trans_id, account, deposit_currency_name, amount, subscription_date, '到期日期必须晚于开立日期')

    is_cld = account.account_type.value == 'CURRENCY_LINKED_DEPOSIT'
    deposit = TimeDeposit(
        status=DepositStatus.IN_PROGRESS,
        account_id=account_id,
        deposit_currency_name=deposit_currency_name,
        amount=round(amount, 2),
        interest_rate=interest_rate,
        subscription_date=subscription_date,
        maturity_date=maturity_date,
    )
    if is_cld:
        deposit.linked_currency_name = (request.form.get('linked_currency_name', '') or '').strip().upper() or None
        deposit.linked_currency_amount = request.form.get('linked_currency_amount', type=float)
        deposit.strike_rate = request.form.get('strike_rate', type=float)

    db.session.add(deposit)
    db.session.flush()

    if transaction and transaction.trans_account_id == account_id:
        transaction.trans_deposit_id = deposit.deposit_id
    else:
        transaction = None

    db.session.commit()

    flash('定期存款已记录')
    return redirect(url_for('deposits.list_deposits'))


@deposits.route('/deposits/<int:deposit_id>/mature', methods=['POST'])
@login_required
def mature_deposit(deposit_id):
    """定期存款到期（由添加转出交易触发，选择未到期存款后确认）"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置你的个人信息')
        return redirect(url_for('deposits.list_deposits'))

    deposit = db.session.get(TimeDeposit, deposit_id)
    if not deposit:
        flash('定期存款不存在')
        return redirect(url_for('deposits.list_deposits'))

    if deposit.status != DepositStatus.IN_PROGRESS:
        flash('该定期存款已到期')
        return redirect(url_for('deposits.list_deposits'))

    account = deposit.account
    if not account or (account.account_owner_id != owner.owner_id and not current_user.is_adult()):
        flash('无权操作此存款')
        return redirect(url_for('deposits.list_deposits'))

    trans_id = request.form.get('trans_id', type=int)
    transaction = db.session.get(Transaction, trans_id) if trans_id else None
    matured_amount = request.form.get('matured_amount', type=float)
    realized_pnl = request.form.get('realized_pnl', type=float)
    matured_currency_name = (request.form.get('matured_currency_name', '') or deposit.deposit_currency_name).strip().upper()

    if not matured_amount or matured_amount <= 0:
        flash('请填写到期收回金额')
        return redirect(url_for('transactions.dashboard', tab='list-tab', deposit_flow='mature',
                                 deposit_trans_id=trans_id or '',
                                 deposit_account_id=account.account_id,
                                 deposit_account_type=account.account_type.value,
                                 deposit_currency=deposit.deposit_currency_name,
                                 deposit_amount=matured_amount or '',
                                 deposit_date=transaction.trans_datetime.strftime('%Y-%m-%d') if transaction else ''))

    deposit.status = DepositStatus.MATURED
    deposit.matured_amount = round(matured_amount, 2)
    deposit.matured_currency_name = matured_currency_name
    # realized_pnl 仅对以 HKD（基础货币）到期的存款适用，未提供时按 到期金额 - 本金 自动计算
    if matured_currency_name == 'HKD':
        if realized_pnl is None:
            realized_pnl = round(matured_amount - deposit.amount, 2)
        deposit.realized_pnl = round(realized_pnl, 2)

    if transaction:
        transaction.trans_deposit_id = deposit.deposit_id

    db.session.commit()

    flash('定期存款已到期')
    return redirect(url_for('deposits.list_deposits'))
