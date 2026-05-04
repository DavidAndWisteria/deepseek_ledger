import os
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
        
        # 初始化默认分类
        _init_default_categories()

    return app


def _init_default_categories():
    """初始化默认分类"""
    from app.models import Category, CategoryType
    
    if Category.query.first() is not None:
        return
    
    defaults = [
        # 收入类
        ('工资', '职业收入', '主业', CategoryType.INCOME),
        ('兼职', '职业收入', '副业', CategoryType.INCOME),
        ('投资收益', '投资收入', '分红', CategoryType.INCOME),
        ('其他收入', '其他', '其他', CategoryType.INCOME),
        # 支出类
        ('餐饮', '日常生活', '饮食', CategoryType.EXPENSE),
        ('交通', '日常生活', '出行', CategoryType.EXPENSE),
        ('购物', '日常生活', '消费', CategoryType.EXPENSE),
        ('住房', '固定支出', '租金/房贷', CategoryType.EXPENSE),
        ('水电煤', '固定支出', '公用事业', CategoryType.EXPENSE),
        ('通讯', '固定支出', '电话/网络', CategoryType.EXPENSE),
        ('医疗', '健康', '医疗保健', CategoryType.EXPENSE),
        ('教育', '成长', '学习培训', CategoryType.EXPENSE),
        ('娱乐', '休闲', '娱乐消费', CategoryType.EXPENSE),
        ('其他支出', '其他', '其他', CategoryType.EXPENSE),
        # 转账类
        ('账户转账', '转账', '内部转账', CategoryType.TRANSFER),
        # 特殊类
        ('账户初始化', '特殊', '开户', CategoryType.SPECIAL),
    ]
    
    for name, cls, subclass, ctype in defaults:
        cat = Category(
            category_name=name,
            category_class=cls,
            category_subclass=subclass,
            category_type=ctype
        )
        db.session.add(cat)
    
    db.session.commit()