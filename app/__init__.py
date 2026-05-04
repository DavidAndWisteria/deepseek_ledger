import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# 初始化扩展（未绑定app）
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    # 创建Flask应用实例
    app = Flask(__name__)
    
    # 基础配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../instance/ledger.db'  # 数据库存放在instance文件夹
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # 确保instance文件夹存在
    os.makedirs(app.instance_path, exist_ok=True)

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    login_manager.login_view = 'auth.login'  # 登录视图的路由端点
    login_manager.login_message = '请先登录以访问此页面。'

    # 注册蓝图（将路由分组管理）
    from app.routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from app.routes.records import records as records_blueprint
    app.register_blueprint(records_blueprint)

    # 创建数据库表（如果不存在）
    with app.app_context():
        from app import models  # 确保模型被导入
        db.create_all()

    return app