from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Family, User, Owner, UserRole

family = Blueprint('family', __name__)


def get_user_owner():
    """获取当前用户的Owner"""
    if current_user.owner:
        return current_user.owner
    return None


@family.route('/family')
@login_required
def manage_family():
    """家庭管理页面"""
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('transactions.dashboard'))
    
    if not current_user.is_adult():
        flash('仅成人可以管理家庭成员')
        return redirect(url_for('transactions.dashboard'))
    
    family_obj = db.session.get(Family, owner.family_id)
    if not family_obj:
        flash('未找到家庭信息')
        return redirect(url_for('transactions.dashboard'))
    
    # 获取家庭所有成员（排除家庭共享 Owner，即 user_id 为 None 的）
    members = Owner.query.filter(
        Owner.family_id == family_obj.family_id,
        Owner.user_id.isnot(None)
    ).all()
    
    # 获取家庭所有用户
    users = User.query.filter_by(family_id=family_obj.family_id).all()
    
    return render_template(
        'family.html',
        family=family_obj,
        members=members,
        users=users
    )


@family.route('/family/add-member', methods=['POST'])
@login_required
def add_member():
    """添加家庭成员"""
    if not current_user.is_adult():
        flash('仅成人可以添加家庭成员')
        return redirect(url_for('family.manage_family'))
    
    owner = get_user_owner()
    if not owner:
        flash('请先设置个人信息')
        return redirect(url_for('family.manage_family'))
    
    owner_name = request.form.get('owner_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'CHILD')
    
    # 验证
    errors = []
    if not owner_name:
        errors.append('成员名称不能为空')
    if not username or len(username) < 3:
        errors.append('用户名至少3个字符')
    if not password or len(password) < 8:
        errors.append('密码至少8个字符')
    if User.query.filter_by(username=username).first():
        errors.append('用户名已存在')
    
    if errors:
        for error in errors:
            flash(error)
        return redirect(url_for('family.manage_family'))
    
    # 创建用户
    user = User(
        username=username,
        role=UserRole.ADULT if role == 'ADULT' else UserRole.CHILD,
        family_id=owner.family_id
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    
    # 创建Owner
    new_owner = Owner(
        owner_name=owner_name,
        family_id=owner.family_id,
        user_id=user.id
    )
    db.session.add(new_owner)
    db.session.commit()
    
    flash(f'成员 {owner_name} 添加成功！')
    return redirect(url_for('family.manage_family'))


@family.route('/family/edit-member/<int:owner_id>', methods=['POST'])
@login_required
def edit_member(owner_id):
    """编辑家庭成员信息"""
    if not current_user.is_adult():
        flash('仅成人可以编辑家庭成员')
        return redirect(url_for('family.manage_family'))
    
    target_owner = db.session.get(Owner, owner_id)
    if not target_owner:
        flash('成员不存在')
        return redirect(url_for('family.manage_family'))
    
    current_owner = get_user_owner()
    
    # 验证是否同一家庭
    if target_owner.family_id != current_owner.family_id:
        flash('无权编辑此成员')
        return redirect(url_for('family.manage_family'))
    
    owner_name = request.form.get('owner_name', '').strip()
    role = request.form.get('role', 'CHILD')
    
    if not owner_name:
        flash('成员名称不能为空')
        return redirect(url_for('family.manage_family'))
    
    # 更新Owner名称
    target_owner.owner_name = owner_name
    
    # 更新关联用户的角色
    if target_owner.user:
        target_owner.user.role = UserRole.ADULT if role == 'ADULT' else UserRole.CHILD
    
    db.session.commit()
    flash(f'成员 {owner_name} 更新成功！')
    return redirect(url_for('family.manage_family'))


@family.route('/family/delete-member/<int:owner_id>', methods=['POST'])
@login_required
def delete_member(owner_id):
    """删除家庭成员"""
    if not current_user.is_adult():
        flash('仅成人可以删除家庭成员')
        return redirect(url_for('family.manage_family'))
    
    target_owner = db.session.get(Owner, owner_id)
    if not target_owner:
        flash('成员不存在')
        return redirect(url_for('family.manage_family'))
    
    current_owner = get_user_owner()
    
    # 验证是否同一家庭
    if target_owner.family_id != current_owner.family_id:
        flash('无权删除此成员')
        return redirect(url_for('family.manage_family'))
    
    # 不能删除自己
    if target_owner.owner_id == current_owner.owner_id:
        flash('不能删除自己')
        return redirect(url_for('family.manage_family'))
    
    # 检查是否还有其他成人
    if target_owner.user and target_owner.user.is_adult():
        adult_count = User.query.filter_by(
            family_id=current_owner.family_id,
            role=UserRole.ADULT
        ).count()
        if adult_count <= 1:
            flash('家庭至少需要一位成人成员')
            return redirect(url_for('family.manage_family'))
    
    # 删除关联用户（如果存在）
    if target_owner.user:
        db.session.delete(target_owner.user)
    
    # 删除Owner
    db.session.delete(target_owner)
    db.session.commit()
    
    flash(f'成员 {target_owner.owner_name} 已删除')
    return redirect(url_for('family.manage_family'))


@family.route('/family/reset-password/<int:owner_id>', methods=['POST'])
@login_required
def reset_member_password(owner_id):
    """重置成员密码（仅成人可操作）"""
    if not current_user.is_adult():
        flash('仅成人可以重置密码')
        return redirect(url_for('family.manage_family'))
    
    target_owner = db.session.get(Owner, owner_id)
    if not target_owner:
        flash('成员不存在')
        return redirect(url_for('family.manage_family'))
    
    current_owner = get_user_owner()
    
    if target_owner.family_id != current_owner.family_id:
        flash('无权操作此成员')
        return redirect(url_for('family.manage_family'))
    
    if not target_owner.user:
        flash('该成员没有关联用户账户')
        return redirect(url_for('family.manage_family'))
    
    new_password = request.form.get('new_password', '')
    if len(new_password) < 8:
        flash('密码至少8个字符')
        return redirect(url_for('family.manage_family'))
    
    target_owner.user.set_password(new_password)
    db.session.commit()
    
    flash(f'成员 {target_owner.owner_name} 的密码已重置')
    return redirect(url_for('family.manage_family'))