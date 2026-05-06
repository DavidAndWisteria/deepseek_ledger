import csv
import io
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, session
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from app import db
from app.models import (
    Account, Category, Owner, AccountType, CategoryType,
    BluecoinsAccountMapping, BluecoinsCategoryMapping
)
from app.services.import_service import ImportService

importer = Blueprint('importer', __name__)


@importer.route('/import')
@login_required
def import_page():
    """导入页面"""
    # 清除之前的下载缓存
    session.pop('download_csv', None)
    return render_template('import.html')


@importer.route('/import/accounts', methods=['POST'])
@login_required
def import_accounts():
    """导入账户 CSV"""
    if 'file' not in request.files:
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    file = request.files['file']
    if file.filename == '':
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    try:
        content = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        flash('文件编码错误，请使用 UTF-8 编码')
        return redirect(url_for('importer.import_page'))
    
    service = ImportService(current_user)
    result = service.import_accounts_csv(content)
    
    flash(f'账户导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}')
    return redirect(url_for('importer.import_page'))


@importer.route('/import/categories', methods=['POST'])
@login_required
def import_categories():
    """导入分类 CSV"""
    if 'file' not in request.files:
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    file = request.files['file']
    if file.filename == '':
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    try:
        content = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        flash('文件编码错误，请使用 UTF-8 编码')
        return redirect(url_for('importer.import_page'))
    
    service = ImportService(current_user)
    result = service.import_categories_csv(content)
    
    flash(f'分类导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}')
    return redirect(url_for('importer.import_page'))


@importer.route('/import/transactions/upload', methods=['POST'])
@login_required
def upload_transactions():
    """上传交易 CSV 并预览"""
    if 'file' not in request.files:
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    file = request.files['file']
    if file.filename == '':
        flash('请选择文件')
        return redirect(url_for('importer.import_page'))
    
    try:
        content = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        flash('文件编码错误，请使用 UTF-8 编码')
        return redirect(url_for('importer.import_page'))
    
    session['import_csv_content'] = content
    
    service = ImportService(current_user)
    
    try:
        service.import_transactions_csv(content)
        skipped, missing_accounts, missing_categories = service.get_skipped_transactions()
        summary = service.get_summary()
    except Exception:
        from app import db
        db.session.rollback()
        flash('文件解析失败，请检查格式')
        return redirect(url_for('importer.import_page'))
    
    # 查询现有账户和分类列表供手动映射使用
    owner = current_user.owner
    family_owner_ids = [o.owner_id for o in Owner.query.filter_by(family_id=owner.family_id).all()]
    accounts = Account.query.filter(
        Account.account_owner_id.in_(family_owner_ids)
    ).order_by(Account.account_type, Account.account_custodian, Account.account_name).all()
    
    all_categories = Category.query.order_by(
        Category.category_type, Category.category_class, Category.category_subclass
    ).all()
    
    members = Owner.query.filter_by(family_id=owner.family_id).all()
    
    return render_template(
        'import.html',
        preview=True,
        summary=summary,
        skipped=skipped,
        missing_accounts=missing_accounts,
        missing_categories=missing_categories,
        skipped_count=len(skipped),
        accounts=accounts,
        all_categories=all_categories,
        members=members,
        current_owner=owner
    )


@importer.route('/import/transactions/confirm', methods=['POST'])
@login_required
def confirm_transactions():
    """确认导入交易（含手动映射和即时创建）"""
    content = session.get('import_csv_content', '')
    if not content:
        flash('请先上传文件')
        return redirect(url_for('importer.import_page'))
    
    service = ImportService(current_user)
    
    # 收集手动映射
    manual_mappings = {'accounts': {}, 'categories': {}}
    
    # 第一步：处理即时创建账户
    for key, value in request.form.items():
        if key.startswith('new_account_') and value:
            bc_name = key.replace('new_account_', '')
            account_name = value.strip()
            if account_name:
                other_name = request.form.get(f'new_acct_other_{bc_name}', '').strip() or None
                custodian = request.form.get(f'new_acct_custodian_{bc_name}', '导入创建').strip()
                acct_type_str = request.form.get(f'new_acct_type_{bc_name}', 'SAVING').strip()
                currency = request.form.get(f'new_acct_currency_{bc_name}', 'HKD').strip()
                owner_id = request.form.get(f'new_acct_owner_{bc_name}', type=int) or current_user.owner.owner_id
                
                create_date_str = request.form.get(f'new_acct_create_date_{bc_name}', '')
                close_date_str = request.form.get(f'new_acct_close_date_{bc_name}', '')
                
                create_date = None
                if create_date_str:
                    try:
                        create_date = datetime.strptime(create_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                if not create_date:
                    create_date = datetime.now(timezone.utc).date()
                
                close_date = None
                if close_date_str:
                    try:
                        close_date = datetime.strptime(close_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                try:
                    acct_type = AccountType[acct_type_str]
                except KeyError:
                    acct_type = AccountType.SAVING
                
                account = Account(
                    account_name=account_name,
                    account_other_name=other_name,
                    account_type=acct_type,
                    account_create_date=create_date,
                    account_close_date=close_date,
                    account_custodian=custodian,
                    account_currency_name=currency,
                    account_owner_id=owner_id
                )
                db.session.add(account)
                db.session.flush()
                
                mapping = BluecoinsAccountMapping(
                    bluecoins_name=bc_name,
                    account_id=account.account_id,
                    owner_id=current_user.owner.owner_id,
                    is_manual=True
                )
                db.session.add(mapping)
                db.session.flush()
                
                # 加入 service 的映射字典
                service.account_map[bc_name] = account.account_id
                service.new_account_mappings[bc_name] = account.account_id
    
    # 第二步：处理即时创建分类
    for key, value in request.form.items():
        if key.startswith('new_category_') and value:
            key_str = key.replace('new_category_', '')
            parts = key_str.split('|||')
            if len(parts) == 5 and value.strip():
                bc_year, bc_type, bc_group, bc_category, bc_title = parts
                category_name = value.strip()
                
                cat_class = request.form.get(f'new_cat_class_{key_str}', bc_group).strip()
                cat_subclass = request.form.get(f'new_cat_subclass_{key_str}', bc_category).strip()
                cat_type_str = request.form.get(f'new_cat_type_{key_str}', 'E').strip()
                
                try:
                    cat_type = CategoryType(cat_type_str)
                except ValueError:
                    cat_type = CategoryType.E
                
                cat = Category(
                    category_name=category_name,
                    category_class=cat_class,
                    category_subclass=cat_subclass,
                    category_type=cat_type
                )
                db.session.add(cat)
                db.session.flush()
                
                cat_mapping = BluecoinsCategoryMapping(
                    bluecoins_year=bc_year,
                    bluecoins_type=bc_type,
                    bluecoins_group=bc_group,
                    bluecoins_category=bc_category,
                    bluecoins_title=bc_title,
                    category_id=cat.category_id,
                    is_manual=True
                )
                db.session.add(cat_mapping)
                db.session.flush()
                
                # 加入 service 的映射字典
                mapping_key = (bc_year, bc_type, bc_group, bc_category, bc_title)
                service.category_map[mapping_key] = cat.category_id
                service.new_category_mappings[mapping_key] = cat.category_id
    
    # 提交即时创建的账户和分类
    db.session.commit()
    
    # 第三步：收集手动映射（选择现有账户/分类的）
    for key, value in request.form.items():
        if key.startswith('map_account_') and value and value != '__new__':
            bc_name = key.replace('map_account_', '')
            manual_mappings['accounts'][bc_name] = value
        elif key.startswith('map_category_') and value and value != '__new__':
            key_str = key.replace('map_category_', '')
            manual_mappings['categories'][key_str] = value
    
    skip_unmatched = request.form.get('skip_unmatched') == '1'
    
    # 第四步：导入交易（使用同一个 service 实例）
    result = service.import_transactions_csv(content, manual_mappings)
    
    if skip_unmatched:
        flash(f'交易导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}')
    else:
        flash(f'交易导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}')
    
    csv_content = service.get_skipped_csv()
    if csv_content:
        session['download_csv'] = csv_content
        session['download_skipped_count'] = len(service.skipped_transactions)
    
    session.pop('import_csv_content', None)
    
    return redirect(url_for('importer.import_page'))


@importer.route('/import/download-skipped')
@login_required
def download_skipped():
    """下载跳过的交易 CSV"""
    csv_content = session.get('download_csv', '')
    if not csv_content:
        flash('没有可下载的内容')
        return redirect(url_for('importer.import_page'))
    
    session.pop('download_csv', None)
    session.pop('download_skipped_count', None)
    
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=skipped_transactions.csv'}
    )