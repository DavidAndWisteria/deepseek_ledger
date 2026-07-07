"""
数据库查询工具 - 支持查询任意表
使用方法：在项目根目录运行 python scripts/query_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import (
    Transaction, Account, Category, Owner, User, Family,
    BluecoinsAccountMapping, BluecoinsCategoryMapping,
    TransactionStatus, AccountType, CategoryType, UserRole
)
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text


def show_tables():
    """显示所有表名和行数"""
    app = create_app()
    with app.app_context():
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        print(f"\n{'='*60}")
        print(f"数据库表清单")
        print(f"{'='*60}")
        print(f"{'表名':<35} {'行数':>10}")
        print(f"{'-'*60}")
        
        total = 0
        for table in tables:
            result = db.session.execute(text(f"SELECT COUNT(*) FROM [{table}]"))
            count = result.scalar() or 0
            total += count
            print(f"{table:<35} {count:>10}")
        
        print(f"{'-'*60}")
        print(f"{'总计':<35} {total:>10}")
        print(f"{'='*60}\n")


def query_table(table_name, limit=50):
    """查询任意表的全部数据"""
    app = create_app()
    
    table_map = {
        'family': Family,
        'user': User,
        'owner': Owner,
        'account': Account,
        'category': Category,
        'transaction': Transaction,
        'bluecoins_account_mapping': BluecoinsAccountMapping,
        'bluecoins_category_mapping': BluecoinsCategoryMapping,
    }
    
    model = table_map.get(table_name.lower())
    if not model:
        print(f"未知表: {table_name}")
        print(f"可用表: {', '.join(table_map.keys())}")
        return
    
    with app.app_context():
        # SQLAlchemy 2.0 风格查询
        stmt = select(model).limit(limit)
        rows = db.session.scalars(stmt).all()
        
        print(f"\n{'='*120}")
        print(f"{table_name} (共 {len(rows)} 条, 限制 {limit} 条)")
        print(f"{'='*120}")
        
        if not rows:
            print("(空)")
            print(f"{'='*120}\n")
            return
        
        # 打印列名
        columns = [c.name for c in model.__table__.columns]
        col_widths = {c: max(len(c), 12) for c in columns}
        
        # 计算列宽
        for row in rows:
            for c in columns:
                val = str(getattr(row, c, '')) if getattr(row, c, '') is not None else ''
                col_widths[c] = min(max(col_widths[c], len(val)), 30)
        
        # 打印表头
        header = ' | '.join(f"{c:<{col_widths[c]}}" for c in columns)
        print(header)
        print('-' * len(header))
        
        # 打印数据
        for row in rows:
            values = []
            for c in columns:
                val = getattr(row, c, None)
                if val is None:
                    val_str = ''
                elif isinstance(val, datetime):
                    val_str = val.strftime('%Y-%m-%d %H:%M')
                else:
                    val_str = str(val)[:col_widths[c]]
                values.append(f"{val_str:<{col_widths[c]}}")
            print(' | '.join(values))
        
        print(f"{'='*120}\n")


def query_sql(sql, limit=100):
    """执行自定义 SQL 查询"""
    app = create_app()
    with app.app_context():
        try:
            result = db.session.execute(text(sql))
            rows = result.fetchall()
            
            if rows:
                columns = result.keys()
                print(f"\n查询结果 ({len(rows)} 条):")
                for row in rows[:limit]:
                    print(dict(zip(columns, row)))
                if len(rows) > limit:
                    print(f"... 还有 {len(rows) - limit} 条未显示")
            else:
                print("\n查询无结果")
        except Exception as e:
            print(f"SQL 错误: {e}")


if __name__ == '__main__':
    # ==========================================
    # 查看所有表及行数
    # ==========================================
    # show_tables()
    
    # ==========================================
    # 查询指定表（取消注释使用）
    # ==========================================
    
    # query_table('transaction', limit=20)
    # query_table('account')
    # query_table('category')
    # query_table('owner')
    # query_table('user')
    # query_table('family')
    # query_table('bluecoins_account_mapping')
    # query_table('bluecoins_category_mapping')
    
    # ==========================================
    # 执行自定义 SQL（取消注释使用）
    # ==========================================

    print("count transaction")
    query_sql("SELECT count(*) FROM [transaction]")
    print("count account")
    query_sql("SELECT count(*) FROM account")
    print("count account mapping")    
    query_sql("SELECT count(*) FROM bluecoins_account_mapping")
    print("show new mapping details")
    query_sql("SELECT * FROM bluecoins_account_mapping WHERE is_manual = true")
    query_sql("SELECT * FROM account WHERE account_id in (SELECT account_id FROM bluecoins_account_mapping WHERE is_manual = true)")
    

    query_sql("SELECT count(*) FROM bluecoins_category_mapping")
    # query_sql("SELECT * FROM [transaction] WHERE trans_amount > 1000 LIMIT 10")
    # query_sql("SELECT category_type, COUNT(*) as cnt FROM category GROUP BY category_type")

    # ==========================================
    # 删除指定表
    # ==========================================

    # query_sql("DROP TABLE bluecoins_account_mapping")
    # query_sql("DROP TABLE account")