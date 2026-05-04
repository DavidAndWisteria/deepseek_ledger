from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Account, AccountType, Owner

accounts = Blueprint('accounts', __name__)


def get_user_owner():
    if current_user.owner:
        return current_user.owner
    return None


def get_family_members():
    owner = get_user_owner()
    if not owner:
        return []
    return Owner.query.filter_by(family_id=owner.family_id).all()


@accounts.route('/accounts')
@login_required
def list_accounts():
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('transactions.dashboard'))
    
    if current_user.can_view_family_data():
        family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
        accounts_list = Account.query.filter(Account.account_owner_id.in_(family_owner_ids)).order_by(Account.account_create_date.desc()).all()
    else:
        accounts_list = Account.query.filter_by(account_owner_id=owner.owner_id).order_by(Account.account_create_date.desc()).all()
    
    members = get_family_members()
    
    return render_template(
        'accounts.html',
        accounts=accounts_list,
        account_types=AccountType,
        members=members,
        current_owner=owner
    )


@accounts.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
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
    
    # 确定拥有者：成人可为家庭其他成员创建账户
    owner_id = request.form.get('account_owner_id', type=int)
    if not owner_id or not current_user.is_adult():
        owner_id = owner.owner_id
    else:
        target_owner = db.session.get(Owner, owner_id)
        if not target_owner or target_owner.family_id != owner.family_id:
            owner_id = owner.owner_id
    
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
    
    account = Account(
        account_name=account_name,
        account_other_name=account_other_name if account_other_name else None,
        account_type=AccountType[account_type],
        account_create_date=create_date,
        account_close_date=close_date,
        account_custodian=account_custodian,
        account_currency_name=currency,
        account_owner_id=owner_id
    )
    db.session.add(account)
    db.session.commit()
    flash('账户添加成功')
    return redirect(url_for('accounts.list_accounts'))


@accounts.route('/accounts/<int:account_id>/edit', methods=['POST'])
@login_required
def edit_account(account_id):
    owner = get_user_owner()
    account = db.session.get(Account, account_id)
    if not account:
        flash('账户不存在')
        return redirect(url_for('accounts.list_accounts'))
    
    # 权限检查：本人或成人可编辑
    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        flash('无权修改此账户')
        return redirect(url_for('accounts.list_accounts'))
    
    account.account_name = request.form.get('account_name', account.account_name).strip()
    account.account_other_name = request.form.get('account_other_name', '').strip() or None
    account.account_custodian = request.form.get('account_custodian', account.account_custodian).strip()
    
    # 更新日期
    create_date_str = request.form.get('account_create_date', '')
    if create_date_str:
        try:
            account.account_create_date = datetime.strptime(create_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    
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
    return redirect(url_for('accounts.list_accounts'))


@accounts.route('/accounts/<int:account_id>/delete', methods=['POST'])
@login_required
def delete_account(account_id):
    owner = get_user_owner()
    account = db.session.get(Account, account_id)
    if not account:
        flash('账户不存在')
        return redirect(url_for('accounts.list_accounts'))
    
    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        flash('无权删除此账户')
        return redirect(url_for('accounts.list_accounts'))
    
    db.session.delete(account)
    db.session.commit()
    flash('账户已删除')
    return redirect(url_for('accounts.list_accounts'))