from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Account, AccountType, Owner

accounts = Blueprint('accounts', __name__)


def get_user_owner():
    if current_user.owner:
        return current_user.owner
    return None


@accounts.route('/accounts')
@login_required
def list_accounts():
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('transactions.dashboard'))
    
    accounts_list = Account.query.filter_by(account_owner_id=owner.owner_id).all()
    return render_template('accounts.html', accounts=accounts_list, account_types=AccountType)


@accounts.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('accounts.list_accounts'))
    
    account_name = request.form.get('account_name', '')
    account_type = request.form.get('account_type', 'SAVING')
    account_custodian = request.form.get('account_custodian', '')
    account_other_name = request.form.get('account_other_name', '')
    currency = request.form.get('currency', 'HKD')
    
    if not account_name or not account_custodian:
        flash('请填写账户名称和机构')
        return redirect(url_for('accounts.list_accounts'))
    
    account = Account(
        account_name=account_name,
        account_other_name=account_other_name if account_other_name else None,
        account_type=AccountType[account_type],
        account_custodian=account_custodian,
        account_currency_name=currency,
        account_owner_id=owner.owner_id
    )
    db.session.add(account)
    db.session.commit()
    flash('账户添加成功')
    return redirect(url_for('accounts.list_accounts'))


@accounts.route('/accounts/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    owner = get_user_owner()
    account = Account.query.get_or_404(account_id)
    
    if account.account_owner_id != owner.owner_id:
        flash('无权删除此账户')
        return redirect(url_for('accounts.list_accounts'))
    
    db.session.delete(account)
    db.session.commit()
    flash('账户已删除')
    return redirect(url_for('accounts.list_accounts'))


@accounts.route('/accounts/<int:account_id>/edit', methods=['POST'])
@login_required
def edit_account(account_id):
    owner = get_user_owner()
    account = Account.query.get_or_404(account_id)
    
    if account.account_owner_id != owner.owner_id:
        flash('无权修改此账户')
        return redirect(url_for('accounts.list_accounts'))
    
    account.account_name = request.form.get('account_name', account.account_name)
    account.account_other_name = request.form.get('account_other_name', account.account_other_name)
    account.account_custodian = request.form.get('account_custodian', account.account_custodian)
    
    db.session.commit()
    flash('账户更新成功')
    return redirect(url_for('accounts.list_accounts'))