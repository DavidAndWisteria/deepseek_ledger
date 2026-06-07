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
    """导入页面 - 不清除下载缓存"""
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
        flash('文件编码错误')
        return redirect(url_for('importer.import_page'))
    
    session['import_csv_content'] = content
    
    service = ImportService(current_user)
    
    # 保存点：预览后回滚
    savepoint = db.session.begin_nested()
    
    try:
        service.import_transactions_csv(content, dry_run=True)
        skipped, missing_accounts, missing_categories = service.get_skipped_transactions()
        summary = service.get_summary()
    except Exception as e:
        db.session.rollback()
        flash('文件解析失败，请检查格式')
        return redirect(url_for('importer.import_page'))
    
    # 回滚预览数据
    savepoint.rollback()
    
    # 查询现有账户和分类列表供手动映射
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
    content = session.get('import_csv_content', '')
    if not content:
        flash('请先上传文件')
        return redirect(url_for('importer.import_page'))
    
    service = ImportService(current_user)
    
    skip_unmatched = request.form.get('skip_unmatched') == '1'
    
    manual_mappings = {'accounts': {}, 'categories': {}}
    skipped_accounts = set()
    skipped_categories = set()
    
    for key, value in request.form.items():
        if key.startswith('map_account_'):
            bc_name = key.replace('map_account_', '')
            if value and value != '__new__':
                manual_mappings['accounts'][bc_name] = value
            elif not value:
                skipped_accounts.add(bc_name)
        elif key.startswith('map_category_'):
            key_str = key.replace('map_category_', '')
            if value and value != '__new__':
                manual_mappings['categories'][key_str] = value
            elif not value:
                skipped_categories.add(key_str)
    
    if not skip_unmatched:
        for key, value in request.form.items():
            if key.startswith('new_account_') and value:
                bc_name = key.replace('new_account_', '')
                if not bc_name or not value.strip():
                    continue
                if bc_name not in skipped_accounts:
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
                            is_manual=True
                        )
                        db.session.add(mapping)
                        db.session.flush()
                        service.account_map[bc_name] = account.account_id
        
        for key, value in request.form.items():
            if key.startswith('new_category_') and value:
                key_str = key.replace('new_category_', '')
                parts = key_str.split('|||')
                if len(parts) != 5:
                    continue  # 跳过格式不正确的 key
                if not value.strip():
                    continue
                if key_str in skipped_categories:
                    continue
                if len(parts) == 5 and value.strip():
                    if key_str not in skipped_categories:
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
                        mapping_key = (bc_year, bc_type, bc_group, bc_category, bc_title)
                        service.category_map[mapping_key] = cat.category_id
        
        db.session.commit()
    
    print(f"DEBUG manual_mappings: accounts={manual_mappings['accounts']}")
    print(f"DEBUG manual_mappings: categories={manual_mappings['categories']}")
    print(f"DEBUG skipped_accounts={skipped_accounts}")
    print(f"DEBUG skipped_categories={skipped_categories}")

    result = service.import_transactions_csv(
        content, manual_mappings,
        skipped_accounts=skipped_accounts,
        skipped_categories=skipped_categories
    )
    
    flash(f'交易导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}')
    
    csv_content = service.get_skipped_csv()
    if csv_content:
        session['download_csv'] = csv_content
        session['download_skipped_count'] = len(service.skipped_transactions)
    
    session.pop('import_csv_content', None)
    return redirect(url_for('importer.import_page'))


# download_skipped 路由
@importer.route('/import/download-skipped')
@login_required
def download_skipped():
    csv_content = session.get('download_csv', '')
    if not csv_content:
        flash('没有可下载的内容')
        return redirect(url_for('importer.import_page'))
    
    # 下载后清除
    session.pop('download_csv', None)
    session.pop('download_skipped_count', None)
    
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=skipped_transactions.csv'}
    )