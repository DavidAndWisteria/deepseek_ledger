import re
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Family, Owner, UserRole

auth = Blueprint('auth', __name__)


def sanitize_input(text):
    import bleach
    if text:
        return bleach.clean(text, tags=[], strip=True)
    return ''


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('transactions.dashboard'))
    
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        family_name = request.form.get('family_name', '').strip()
        owner_name = request.form.get('owner_name', '').strip()
        role = request.form.get('role', 'ADULT')
        
        # 验证
        errors = []
        if not username or len(username) < 3:
            errors.append('用户名至少3个字符')
        if not password or len(password) < 8:
            errors.append('密码至少8个字符')
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('用户名只能包含字母、数字和下划线')
        if User.query.filter_by(username=username).first():
            errors.append('用户名已存在')
        if not family_name:
            errors.append('家庭名称不能为空')
        if not owner_name:
            errors.append('成员名称不能为空')
        
        if errors:
            for error in errors:
                flash(error)
            return render_template('register.html')
        
        # 创建家庭
        family = Family(family_name=family_name)
        db.session.add(family)
        db.session.flush()
        
        # 创建用户
        user = User(
            username=username,
            role=UserRole.ADULT if role == 'ADULT' else UserRole.CHILD,
            family_id=family.family_id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        
        # 创建Owner
        owner = Owner(
            owner_name=owner_name,
            family_id=family.family_id,
            user_id=user.id
        )
        db.session.add(owner)
        db.session.commit()
        
        login_user(user)
        flash('注册成功！')
        return redirect(url_for('transactions.dashboard'))
    
    return render_template('register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('transactions.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('登录成功！')
            return redirect(url_for('transactions.dashboard'))
        flash('用户名或密码错误')
    
    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录')
    return redirect(url_for('auth.login'))