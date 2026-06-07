import os
import shutil
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required
from sqlalchemy import text
from app import db

data_manager = Blueprint('data_manager', __name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.path.join(PROJECT_DIR, 'instance', 'ledger.db')
BACKUP_DIR = os.path.join(PROJECT_DIR, 'instance', 'backups')


# ===============================================================
# 数据备份
# ===============================================================

@data_manager.route('/data')
@login_required
def data_page():
    """数据管理页面"""
    # 获取备份列表
    backups = []
    if os.path.exists(BACKUP_DIR):
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')]
        files.sort(reverse=True)
        for f in files:
            path = os.path.join(BACKUP_DIR, f)
            size = os.path.getsize(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
            backups.append({
                'filename': f,
                'size': f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB',
                'mtime': mtime
            })
    
    return render_template('data_manager.html', backups=_get_backups(), active_tab='backup')


@data_manager.route('/data/backup', methods=['POST'])
@login_required
def create_backup():
    """创建数据库备份"""
    if not os.path.exists(DB_FILE):
        flash('数据库文件不存在')
        return redirect(url_for('data_manager.data_page'))
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'ledger_{timestamp}.db')
    
    shutil.copy2(DB_FILE, backup_file)
    flash(f'备份成功: ledger_{timestamp}.db')
    return redirect(url_for('data_manager.data_page'))


@data_manager.route('/data/restore', methods=['POST'])
@login_required
def restore_backup():
    """从备份恢复数据库"""
    backup_name = request.form.get('backup_name', '')
    if not backup_name:
        flash('请选择备份文件')
        return redirect(url_for('data_manager.data_page'))
    
    backup_file = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_file):
        flash('备份文件不存在')
        return redirect(url_for('data_manager.data_page'))
    
    # 恢复前先备份当前数据库
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pre_restore = os.path.join(BACKUP_DIR, f'ledger_before_restore_{timestamp}.db')
        shutil.copy2(DB_FILE, pre_restore)
    
    shutil.copy2(backup_file, DB_FILE)
    flash(f'已从 {backup_name} 恢复数据库')
    return redirect(url_for('data_manager.data_page'))


@data_manager.route('/data/delete-backup', methods=['POST'])
@login_required
def delete_backup():
    """删除指定备份"""
    backup_name = request.form.get('backup_name', '')
    if not backup_name:
        flash('请选择备份文件')
        return redirect(url_for('data_manager.data_page'))
    
    backup_file = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_file):
        flash('备份文件不存在')
        return redirect(url_for('data_manager.data_page'))
    
    os.remove(backup_file)
    flash(f'已删除: {backup_name}')
    return redirect(url_for('data_manager.data_page'))


# ===============================================================
# 数据库查询
# ===============================================================

@data_manager.route('/data/query', methods=['POST'])
@data_manager.route('/data/query', methods=['POST'])
@login_required
def execute_query():
    sql = request.form.get('sql', '').strip()
    if not sql:
        flash('请输入 SQL 语句')
        return redirect(url_for('data_manager.data_page'))
    
    try:
        result = db.session.execute(text(sql))
        
        if result.returns_rows:
            rows = result.fetchall()
            columns = list(result.keys()) if rows else []
            display_rows = rows[:200]
            total_rows = len(rows)
            
            return render_template(
                'data_manager.html',
                query_result={
                    'columns': columns,
                    'rows': [tuple(row) for row in display_rows],
                    'total': total_rows,
                    'displayed': len(display_rows)
                },
                query_sql=sql,
                backups=_get_backups(),
                active_tab='query'
            )
        else:
            db.session.commit()
            flash('SQL 执行成功')
            return redirect(url_for('data_manager.data_page'))
    except Exception as e:
        flash(f'SQL 错误: {str(e)}')
        return render_template(
            'data_manager.html',
            query_sql=sql,
            backups=_get_backups(),
            active_tab='query'
        )


def _get_backups():
    """获取备份列表"""
    backups = []
    if os.path.exists(BACKUP_DIR):
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')]
        files.sort(reverse=True)
        for f in files:
            path = os.path.join(BACKUP_DIR, f)
            size = os.path.getsize(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
            backups.append({
                'filename': f,
                'size': f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB',
                'mtime': mtime
            })
    return backups