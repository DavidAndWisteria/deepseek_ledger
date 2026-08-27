import csv
import io
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, session
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import select
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
        savepoint.rollback()
        flash('文件解析失败，请检查格式')
        return redirect(url_for('importer.import_page'))
    
    # 回滚预览数据
    savepoint.rollback()
    
    # 查询现有账户和分类列表供手动映射
    owner = current_user.owner
    # 替换 Owner.query.filter_by -> select(Owner).where
    family_owner_stmt = select(Owner).where(Owner.family_id == owner.family_id)
    family_owners = db.session.execute(family_owner_stmt).scalars().all()
    family_owner_ids = [o.owner_id for o in family_owners]
    
    # 替换 Account.query.filter -> select(Account).where
    account_stmt = (
        select(Account)
        .where(Account.account_owner_id.in_(family_owner_ids))
        .order_by(Account.account_type, Account.account_custodian, Account.account_name)
    )
    accounts = db.session.execute(account_stmt).scalars().all()
    
    # 替换 Category.query.order_by -> select(Category).order_by
    category_stmt = (
        select(Category)
        .order_by(Category.category_type, Category.category_class, Category.category_subclass)
    )
    all_categories = db.session.execute(category_stmt).scalars().all()
    
    # 替换 Owner.query.filter_by -> select(Owner).where
    members = db.session.execute(
        select(Owner).where(Owner.family_id == owner.family_id)
    ).scalars().all()
    
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
                map_value = request.form.get(f'map_category_{key_str}', '')
                if map_value != '__new__':
                    continue
                parts = key_str.split('|||')
                if len(parts) != 5:
                    continue
                if not value.strip():
                    continue
                if key_str in skipped_categories:
                    continue
                if key_str not in skipped_categories:
                    bc_year, bc_type, bc_group, bc_category, bc_title = parts
                    category_name = value.strip()
                    
                    cat_class = request.form.get(f'new_cat_class_{key_str}', bc_group).strip()
                    cat_subclass = request.form.get(f'new_cat_subclass_{key_str}', bc_category).strip()
                    cat_other = request.form.get(f'new_cat_other_{key_str}', '').strip() or None
                    cat_type_str = request.form.get(f'new_cat_type_{key_str}', 'E').strip()
                    
                    try:
                        cat_type = CategoryType(cat_type_str)
                    except ValueError:
                        cat_type = CategoryType.EXPENSE
                    
                    cat = Category(
                        category_name=category_name,
                        category_other_name=cat_other,
                        category_class=cat_class,
                        category_subclass=cat_subclass,
                        category_type=cat_type
                    )
                    db.session.add(cat)
                    db.session.flush()
                    
                    # 替换 BluecoinsCategoryMapping.query.filter_by(...).first()
                    existing_stmt = (
                        select(BluecoinsCategoryMapping)
                        .where(
                            BluecoinsCategoryMapping.bluecoins_year == bc_year,
                            BluecoinsCategoryMapping.bluecoins_type == bc_type,
                            BluecoinsCategoryMapping.bluecoins_group == bc_group,
                            BluecoinsCategoryMapping.bluecoins_category == bc_category,
                            BluecoinsCategoryMapping.bluecoins_title == bc_title
                        )
                    )
                    existing_mapping = db.session.execute(existing_stmt).scalars().first()
                    if existing_mapping:
                        existing_mapping.category_id = cat.category_id
                        existing_mapping.is_manual = True
                    else:
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
                    for existing_key in list(service.category_map.keys()):
                        if existing_key[1] == bc_type and existing_key[2] == bc_group and \
                           existing_key[3] == bc_category and existing_key[4] == bc_title:
                            del service.category_map[existing_key]
                    service.category_map[mapping_key] = cat.category_id
        
        db.session.commit()
    
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


@importer.route('/import/fund-purchases/upload', methods=['POST'])
@login_required
def upload_fund_purchases():
    """上传基金购买 CSV 并预览（未匹配的账户可手动处理）"""
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

    session['fund_import_csv_content'] = content

    service = ImportService(current_user)
    rows = service.prepare_fund_purchases(content)

    owner = current_user.owner
    family_owner_stmt = select(Owner).where(Owner.family_id == owner.family_id)
    family_owners = db.session.execute(family_owner_stmt).scalars().all()
    family_owner_ids = [o.owner_id for o in family_owners]

    account_stmt = (
        select(Account)
        .where(Account.account_owner_id.in_(family_owner_ids))
        .order_by(Account.account_type, Account.account_custodian, Account.account_name)
    )
    accounts = db.session.execute(account_stmt).scalars().all()

    # 转账交易分类（基金购买生成的转账用），与添加交易页面的转账分类一致
    service._get_transfer_category_id()  # 确保默认转账分类存在
    transfer_category_stmt = (
        select(Category)
        .where(Category.category_type == CategoryType.TRANSFER)
        .order_by(Category.category_class, Category.category_subclass, Category.category_name)
    )
    fund_transfer_categories = db.session.execute(transfer_category_stmt).scalars().all()
    db.session.commit()

    auto_count = sum(1 for r in rows if not r['error'] and r['fund_account_id'] and r['bank_account_id'])
    need_count = len(rows) - auto_count

    return render_template(
        'import.html',
        fund_preview=True,
        fund_rows=rows,
        fund_auto_count=auto_count,
        fund_need_count=need_count,
        accounts=accounts,
        fund_transfer_categories=fund_transfer_categories,
    )


@importer.route('/import/fund-purchases/confirm', methods=['POST'])
@login_required
def confirm_fund_purchases():
    """确认导入基金购买（应用手动映射/跳过）"""
    content = session.get('fund_import_csv_content', '')
    if not content:
        flash('请先上传文件')
        return redirect(url_for('importer.import_page'))

    service = ImportService(current_user)

    skip_unmatched = request.form.get('skip_unmatched') == '1'
    manual_mappings = {}
    skipped_rows = set()

    for key, value in request.form.items():
        if key.startswith('fund_fund_'):
            try:
                row_num = int(key.replace('fund_fund_', ''))
            except ValueError:
                continue
            if value:
                manual_mappings.setdefault(row_num, {})['fund_account_id'] = value
        elif key.startswith('fund_bank_'):
            try:
                row_num = int(key.replace('fund_bank_', ''))
            except ValueError:
                continue
            if value:
                manual_mappings.setdefault(row_num, {})['bank_account_id'] = value
        elif key.startswith('fund_skip_'):
            try:
                row_num = int(key.replace('fund_skip_', ''))
            except ValueError:
                continue
            if value == '1':
                skipped_rows.add(row_num)

    result = service.import_fund_purchases_csv(
        content,
        manual_mappings=manual_mappings,
        skipped_rows=skipped_rows,
        skip_unmatched=skip_unmatched,
        category_id=request.form.get('fund_category', type=int)
    )

    # 跳过原因细分（已存在 / 未处理 / 用户跳过）
    skip_detail = {}
    for d in result['details']:
        if d['status'] != 'skipped':
            continue
        reason = d.get('reason', '')
        if reason == '已存在相同交易':
            label = '已存在'
        elif reason == '用户跳过':
            label = '用户跳过'
        else:
            label = '未处理'
        skip_detail[label] = skip_detail.get(label, 0) + 1

    msg = f'基金购买导入完成：成功 {result["success"]}，跳过 {result["skipped"]}，失败 {result["failed"]}'
    if skip_detail:
        msg += '（' + '、'.join(f'{k} {v}' for k, v in skip_detail.items()) + '）'
    flash(msg)
    session.pop('fund_import_csv_content', None)
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
