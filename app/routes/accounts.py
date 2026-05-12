from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import nullsfirst, case
from app import db
from app.models import Account, AccountType, Owner, BluecoinsAccountMapping, Transaction

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
    return Owner.query.filter_by(family_id=owner.family_id).all()


@accounts.route('/accounts')
@login_required
def list_accounts():
    """账户列表"""
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
        family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
        accounts_list = Account.query.filter(
            Account.account_owner_id.in_(family_owner_ids)
        ).order_by(
            nullsfirst(Account.account_close_date),
            type_order,
            Account.account_owner_id,
            Account.account_custodian,
            Account.account_currency_name,
            Account.account_name,
            Account.account_other_name
        ).all()
    else:
        accounts_list = Account.query.filter_by(
            account_owner_id=owner.owner_id
        ).order_by(
            nullsfirst(Account.account_close_date),
            type_order,
            Account.account_owner_id,
            Account.account_custodian,
            Account.account_currency_name,
            Account.account_name,
            Account.account_other_name
        ).all()
    
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
    """编辑账户"""
    owner = get_user_owner()
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
    return redirect(url_for('accounts.list_accounts'))


@accounts.route('/accounts/<int:account_id>/check-delete')
@login_required
def check_delete_account(account_id):
    """检查账户关联交易（AJAX），返回删除确认弹窗 HTML"""
    owner = get_user_owner()
    account = db.session.get(Account, account_id)
    if not account:
        return '<p style="color: #e74c3c; text-align: center;">账户不存在</p>'
    
    if account.account_owner_id != owner.owner_id and not current_user.is_adult():
        return '<p style="color: #e74c3c; text-align: center;">无权删除此账户</p>'
    
    transaction_count = Transaction.query.filter_by(trans_account_id=account_id).count()
    csrf_token = generate_csrf()
    
    # 无关联交易，直接确认删除
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
    
    # 有关联交易，显示处理选项
    family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
    target_accounts = Account.query.filter(
        Account.account_owner_id.in_(family_owner_ids),
        Account.account_id != account_id
    ).order_by(Account.account_type, Account.account_custodian, Account.account_name).all()
    
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
        count = Transaction.query.filter_by(trans_account_id=account_id).update(
            {'trans_account_id': target_account_id}
        )
        flash(f'已将 {count} 笔交易迁移到 "{target_account.account_name}"')
    else:
        # 删除所有关联交易（含转账配对）
        transactions = Transaction.query.filter_by(trans_account_id=account_id).all()
        count = len(transactions)
        for t in transactions:
            if t.trans_counter_id:
                counter = db.session.get(Transaction, t.trans_counter_id)
                if counter:
                    db.session.delete(counter)
            db.session.delete(t)
        flash(f'已删除 {count} 笔关联交易')
    
    # 删除 Bluecoins 映射
    BluecoinsAccountMapping.query.filter_by(account_id=account_id).delete()
    
    # 删除账户
    db.session.delete(account)
    db.session.commit()
    flash('账户已删除')
    return redirect(url_for('accounts.list_accounts'))