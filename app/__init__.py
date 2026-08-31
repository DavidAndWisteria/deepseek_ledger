import os
import datetime as dt
from flask import Flask, has_request_context
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
    
    login_manager.login_view = 'auth.login' # type: ignore
    login_manager.login_message = '请先登录以访问此页面。'

    # 模板全局变量
    @app.context_processor
    def utility_processor():
        def get_nav_params():
            if has_request_context():
                from flask import request as req
                return {k: v for k in ('start_date', 'end_date') if (v := req.args.get(k, ''))}
            return {}
        return {
            'today_date': lambda: dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d'),
            'nav_params': get_nav_params(),
        }

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

    from app.routes.deposits import deposits as deposits_blueprint
    app.register_blueprint(deposits_blueprint)

    # 创建数据库表
    with app.app_context():
        from sqlalchemy import inspect
        from app.models import Base
        
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        metadata = Base.metadata
        
        if not existing_tables:
            # 全新数据库，直接创建所有表
            metadata.create_all(db.engine)
        else:
            # 0.3.4: account_balance.account_fx_cost_rate → account_unit_cost_rate
            if 'account_balance' in existing_tables:
                existing_cols = {c['name'] for c in inspector.get_columns('account_balance')}
                if 'account_fx_cost_rate' in existing_cols and 'account_unit_cost_rate' not in existing_cols:
                    db.session.execute(db.text(
                        'ALTER TABLE account_balance RENAME COLUMN account_fx_cost_rate TO account_unit_cost_rate'
                    ))
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.8: 统一外汇/单位存储（trans_fx_* → trans_unit / trans_unit_price / trans_unit_name）
            # 非破坏性迁移：仅补齐缺失列、迁移旧数据，再尝试删除旧列
            if 'transaction' in existing_tables:
                existing_cols = {c['name'] for c in inspector.get_columns('transaction')}
                has_old_fx = 'trans_fx_currency_name' in existing_cols
                need_migrate = (
                    has_old_fx or
                    'trans_unit_name' not in existing_cols or
                    'trans_unit_is_fx_ind' not in existing_cols
                )
                if need_migrate:
                    # 1) 补齐缺失列（对旧版本数据库安全）
                    for col, ddl in (
                        ('trans_unit', 'FLOAT'),
                        ('trans_unit_price', 'FLOAT'),
                        ('trans_unit_name', 'VARCHAR(100)'),
                        ('trans_unit_is_fx_ind', 'BOOLEAN'),
                        ('trans_is_rhs_currency_ind', 'BOOLEAN'),
                    ):
                        if col not in existing_cols:
                            db.session.execute(db.text(
                                f'ALTER TABLE "transaction" ADD COLUMN "{col}" {ddl}'
                            ))
                    # 2) 迁移旧 trans_fx_* 数据到统一字段
                    if has_old_fx:
                        db.session.execute(db.text(
                            "UPDATE \"transaction\" SET "
                            "trans_unit = CASE WHEN trans_fx_amount IS NOT NULL THEN trans_fx_amount ELSE trans_unit END, "
                            "trans_unit_price = CASE WHEN trans_fx_amount IS NOT NULL THEN trans_fx_rate ELSE trans_unit_price END, "
                            "trans_unit_name = trans_fx_currency_name, "
                            "trans_unit_is_fx_ind = CASE WHEN trans_fx_currency_name IS NOT NULL THEN 1 ELSE COALESCE(trans_unit_is_fx_ind, 0) END, "
                            "trans_is_rhs_currency_ind = CASE WHEN trans_fx_currency_name IS NOT NULL THEN 1 ELSE trans_is_rhs_currency_ind END"
                        ))
                        # 3) 尽量删除旧列（SQLite 3.35+ 支持）
                        for col in ('trans_fx_currency_name', 'trans_fx_amount', 'trans_fx_rate'):
                            try:
                                db.session.execute(db.text(
                                    f'ALTER TABLE "transaction" DROP COLUMN "{col}"'
                                ))
                            except Exception:
                                pass  # 旧版 SQLite 不支持 DROP COLUMN 时保留旧列
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.9: 拆分外汇/投资单位存储（外汇用 trans_fx_*，投资单位用 trans_unit_*，移除 trans_unit_is_fx_ind）
            # 非破坏性迁移：仅补齐缺失列、回迁外汇数据，再尝试删除标记列
            if 'transaction' in existing_tables:
                tx_cols = {c['name'] for c in inspector.get_columns('transaction')}
                need_fx_split = (
                    'trans_fx_currency_name' not in tx_cols or
                    'trans_fx_rate' not in tx_cols or
                    'trans_fx_amount' not in tx_cols or
                    'trans_unit_is_fx_ind' in tx_cols
                )
                if need_fx_split:
                    # 1) 补齐外汇字段列
                    for col, ddl in (
                        ('trans_fx_currency_name', 'VARCHAR(3)'),
                        ('trans_fx_rate', 'FLOAT'),
                        ('trans_fx_amount', 'FLOAT'),
                    ):
                        if col not in tx_cols:
                            db.session.execute(db.text(
                                f'ALTER TABLE "transaction" ADD COLUMN "{col}" {ddl}'
                            ))
                    # 2) 将原标记为外汇的 trans_unit_* 数据回迁到 trans_fx_*
                    if 'trans_unit_is_fx_ind' in tx_cols:
                        db.session.execute(db.text(
                            "UPDATE \"transaction\" SET "
                            "trans_fx_amount = trans_unit, "
                            "trans_fx_rate = trans_unit_price, "
                            "trans_fx_currency_name = trans_unit_name, "
                            "trans_unit = NULL, "
                            "trans_unit_price = NULL, "
                            "trans_unit_name = NULL "
                            "WHERE trans_unit_is_fx_ind = 1"
                        ))
                        # 3) 尽量删除标记列
                        try:
                            db.session.execute(db.text(
                                'ALTER TABLE "transaction" DROP COLUMN "trans_unit_is_fx_ind"'
                            ))
                        except Exception:
                            pass  # 旧版 SQLite 不支持 DROP COLUMN 时保留旧列
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.9: 账户增加"单位概念"标记（基金账户默认为 True）
            if 'account' in existing_tables:
                acct_cols = {c['name'] for c in inspector.get_columns('account')}
                if 'account_has_unit_ind' not in acct_cols:
                    db.session.execute(db.text(
                        'ALTER TABLE "account" ADD COLUMN "account_has_unit_ind" BOOLEAN NOT NULL DEFAULT 0'
                    ))
                    db.session.execute(db.text(
                        'UPDATE "account" SET "account_has_unit_ind" = 1 WHERE "account_type" = \'FUND\''
                    ))
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.10: 账户增加 ISIN 代码字段（证券/基金唯一标识）
            if 'account' in existing_tables:
                acct_cols = {c['name'] for c in inspector.get_columns('account')}
                if 'account_isin' not in acct_cols:
                    db.session.execute(db.text(
                        'ALTER TABLE "account" ADD COLUMN "account_isin" VARCHAR(12)'
                    ))
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.9: 定期存款表补充账户关联字段
            if 'time_deposit' in existing_tables:
                td_cols = {c['name'] for c in inspector.get_columns('time_deposit')}
                if 'account_id' not in td_cols:
                    db.session.execute(db.text(
                        'ALTER TABLE "time_deposit" ADD COLUMN "account_id" INTEGER'
                    ))
                    db.session.commit()
                    inspector.info_cache.clear()  # 清除缓存以刷新列信息

            # 0.3.11: 清除日终余额缓存（历史版本导入交易未使缓存失效，可能导致余额不含转账交易）
            # account_balance 为纯缓存表，清空后首次查看时自动按最新交易重算
            if 'account_balance' in existing_tables:
                db.session.execute(db.text('DELETE FROM account_balance'))
                db.session.commit()

            # 检查每个模型表的结构
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
                                    except Exception as e:
                                        print(f'[migrate] restore row failed for {table_name}: {e}')
                            db.session.commit()

    return app