import os
import datetime as dt
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# 初始化扩展
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # 基础配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../instance/ledger.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # 确保instance文件夹存在
    os.makedirs(app.instance_path, exist_ok=True)

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录以访问此页面。'

    # 模板全局变量
    @app.context_processor
    def utility_processor():
        return {'today_date': lambda: dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')}

    # 注册蓝图
    from app.routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from app.routes.transactions import transactions as transactions_blueprint
    app.register_blueprint(transactions_blueprint)

    from app.routes.accounts import accounts as accounts_blueprint
    app.register_blueprint(accounts_blueprint)

    from app.routes.categories import categories as categories_blueprint
    app.register_blueprint(categories_blueprint)

    from app.routes.family import family as family_blueprint
    app.register_blueprint(family_blueprint)

    # 创建数据库表
    with app.app_context():
        from app import models
        db.create_all()

    return app