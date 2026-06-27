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

def create_app(test_config=None):
    app = Flask(__name__)
    
    # 基础配置
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///../instance/ledger.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    if test_config:
        app.config.update(test_config)

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

    # 自定义过滤器
    @app.template_filter('amt')
    def format_amount(value, decimals=2, signed=False):
        if value is None:
            return ''
        if signed:
            return '{:+,.{d}f}'.format(value, d=decimals)
        return '{:,.{d}f}'.format(value, d=decimals)

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

    from app.routes.importer import importer as importer_blueprint
    app.register_blueprint(importer_blueprint)

    from app.routes.data_manager import data_manager as data_manager_blueprint
    app.register_blueprint(data_manager_blueprint)

    # 创建数据库表
    with app.app_context():
        from app import models
        from sqlalchemy import inspect, MetaData
        
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        if not existing_tables:
            # 全新数据库，直接创建所有表
            db.create_all()
        else:
            # 检查每个模型表的结构
            metadata = db.metadata
            for table_name, table in metadata.tables.items():
                if table_name not in existing_tables:
                    # 表不存在，直接创建
                    table.create(db.engine)
                else:
                    # 检查列是否匹配
                    existing_columns = {c['name'] for c in inspector.get_columns(table_name)}
                    model_columns = {c.name for c in table.columns}
                    
                    missing_columns = model_columns - existing_columns
                    
                    if missing_columns:
                        # 有缺失列，需要重建表
                        # 1. 备份数据
                        backup_data = None
                        try:
                            result = db.session.execute(table.select())
                            backup_data = [dict(row._mapping) for row in result]
                        except Exception:
                            pass
                        
                        # 2. 删除旧表
                        table.drop(db.engine)
                        
                        # 3. 创建新表
                        table.create(db.engine)
                        
                        # 4. 恢复数据（只恢复存在的列）
                        if backup_data:
                            new_columns = {c.name for c in table.columns}
                            for row in backup_data:
                                filtered_row = {k: v for k, v in row.items() if k in new_columns}
                                if filtered_row:
                                    try:
                                        db.session.execute(table.insert().values(**filtered_row))
                                    except Exception:
                                        pass
                            db.session.commit()

    return app