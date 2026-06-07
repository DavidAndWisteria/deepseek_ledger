"""
数据库备份与恢复工具
使用方法：在项目根目录运行 python scripts/db_backup.py

功能：
  - 自动备份：python scripts/db_backup.py backup
  - 列出备份：python scripts/db_backup.py list
  - 恢复备份：python scripts/db_backup.py restore <备份文件名>
  - 删除备份：python scripts/db_backup.py delete <备份文件名>
"""

import sys
import os
import shutil
from datetime import datetime

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库文件路径
DB_FILE = os.path.join(PROJECT_DIR, 'instance', 'ledger.db')

# 备份目录
BACKUP_DIR = os.path.join(PROJECT_DIR, 'instance', 'backups')


def backup():
    """创建数据库备份"""
    if not os.path.exists(DB_FILE):
        print(f'错误：数据库文件不存在: {DB_FILE}')
        return
    
    # 确保备份目录存在
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # 生成备份文件名（含时间戳）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'ledger_{timestamp}.db')
    
    # 复制数据库文件
    shutil.copy2(DB_FILE, backup_file)
    
    # 显示备份信息
    size = os.path.getsize(backup_file)
    size_str = f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'
    print(f'✅ 备份成功')
    print(f'   文件: {os.path.basename(backup_file)}')
    print(f'   大小: {size_str}')
    print(f'   路径: {backup_file}')


def list_backups():
    """列出所有备份"""
    if not os.path.exists(BACKUP_DIR):
        print('暂无备份')
        return
    
    files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')]
    files.sort(reverse=True)
    
    if not files:
        print('暂无备份')
        return
    
    print(f'备份列表 (共 {len(files)} 个):')
    print(f'{"文件名":<35} {"大小":>10} {"修改时间":>20}')
    print('-' * 70)
    
    for f in files:
        path = os.path.join(BACKUP_DIR, f)
        size = os.path.getsize(path)
        size_str = f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
        print(f'{f:<35} {size_str:>10} {mtime:>20}')


def restore(backup_name):
    """从备份恢复数据库"""
    backup_file = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_file):
        print(f'错误：备份文件不存在: {backup_name}')
        print('可用的备份文件：')
        list_backups()
        return
    
    # 确认操作
    print(f'⚠ 警告：此操作将覆盖当前数据库！')
    print(f'   当前数据库: {DB_FILE}')
    print(f'   恢复为: {backup_file}')
    confirm = input('确认恢复？(输入 yes 确认): ')
    
    if confirm.lower() != 'yes':
        print('已取消')
        return
    
    # 先备份当前数据库
    # if os.path.exists(DB_FILE):
    #     timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    #     pre_restore_backup = os.path.join(BACKUP_DIR, f'ledger_before_restore_{timestamp}.db')
    #     shutil.copy2(DB_FILE, pre_restore_backup)
    #     print(f'📦 已备份当前数据库: {os.path.basename(pre_restore_backup)}')
    
    # 恢复
    shutil.copy2(backup_file, DB_FILE)
    print(f'✅ 恢复成功')


def delete_backup(backup_name):
    """删除指定备份"""
    backup_file = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_file):
        print(f'错误：备份文件不存在: {backup_name}')
        return
    
    confirm = input(f'确认删除 {backup_name}？(输入 yes 确认): ')
    
    if confirm.lower() != 'yes':
        print('已取消')
        return
    
    os.remove(backup_file)
    print(f'✅ 已删除: {backup_name}')


def print_usage():
    """打印使用说明"""
    print('数据库备份与恢复工具')
    print('')
    print('用法:')
    print('  python scripts/db_backup.py backup               创建备份')
    print('  python scripts/db_backup.py list                 列出所有备份')
    print('  python scripts/db_backup.py restore <文件名>      恢复备份')
    print('  python scripts/db_backup.py delete <文件名>       删除备份')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == 'backup':
        backup()
    elif command == 'list':
        list_backups()
    elif command == 'restore':
        if len(sys.argv) < 3:
            print('错误：请指定要恢复的备份文件名')
            list_backups()
        else:
            restore(sys.argv[2])
    elif command == 'delete':
        if len(sys.argv) < 3:
            print('错误：请指定要删除的备份文件名')
            list_backups()
        else:
            delete_backup(sys.argv[2])
    else:
        print(f'未知命令: {command}')
        print_usage()

# #**************************
# # 创建备份
# python scripts/db_backup.py backup

# # 列出所有备份
# python scripts/db_backup.py list

# # 恢复指定备份
# python scripts/db_backup.py restore ledger_20260508_120000.db

# # 删除指定备份
# python scripts/db_backup.py delete ledger_20260508_120000.db