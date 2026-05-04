import re
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
import bleach

auth = Blueprint('auth', __name__)

def sanitize_input(text):
    """简单的输入清洗"""
    if text:
        return bleach.clean(text, tags=[], strip=True)
    return text

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('records.index'))
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        
        # 基本验证
        if not username or not password:
            flash('用户名和密码不能为空')
        elif len(username) < 3 or len(username) > 80:
            flash('用户名长度应在3-80个字符之间')
        elif len(password) < 8:
            flash('密码长度至少为8个字符')
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            flash('用户名只能包含字母、数字和下划线')
        elif User.query.filter_by(username=username).first():
            flash('该用户名已被注册')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('注册成功！')
            return redirect(url_for('records.index'))
    return render_template('register.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('records.index'))
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('登录成功！')
            return redirect(url_for('records.index'))
        flash('用户名或密码错误')
    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录')
    return redirect(url_for('auth.login'))