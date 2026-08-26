import csv
import io
from datetime import datetime, timezone
from flask import current_app
from app import db
from app.models import (
    Account, Category, Transaction, Owner, Family,
    AccountType, CategoryType, TransactionStatus,
    BluecoinsAccountMapping, BluecoinsCategoryMapping
)
from app.routes.accounts import get_fx_rate_to_hkd
from sqlalchemy import select, func


class ImportService:
    """Bluecoins 数据导入服务"""
    
    def __init__(self, current_user):
        self.current_user = current_user
        self.owner = current_user.owner
        self.family_id = current_user.family_id
        
        self.account_map = {}
        self.category_map = {}
        
        self._load_existing_mappings()
        
        self.results = {
            'accounts': {'success': 0, 'skipped': 0, 'failed': 0, 'details': []},
            'categories': {'success': 0, 'skipped': 0, 'failed': 0, 'details': []},
            'transactions': {'success': 0, 'skipped': 0, 'failed': 0, 'details': []},
        }
        
        self.skipped_transactions = []
        self.new_account_mappings = {}
        self.new_category_mappings = {}
    
    def _load_existing_mappings(self):
        """加载已存在的 Bluecoins 映射"""
        # 账户映射
        stmt = select(BluecoinsAccountMapping)
        mappings = db.session.scalars(stmt).all()
        for m in mappings:
            self.account_map[m.bluecoins_name] = m.account_id
        
        # 分类映射
        stmt = select(BluecoinsCategoryMapping)
        cat_mappings = db.session.scalars(stmt).all()
        for m in cat_mappings:
            key = (m.bluecoins_year, m.bluecoins_type, m.bluecoins_group,
                   m.bluecoins_category, m.bluecoins_title)
            self.category_map[key] = m.category_id
        
        manual_mappings = [m for m in cat_mappings if m.is_manual]
        manual_keys = set()
        for m in manual_mappings:
            key = (m.bluecoins_year, m.bluecoins_type, m.bluecoins_group,
                   m.bluecoins_category, m.bluecoins_title)
            manual_keys.add(key)
        for m in manual_mappings:
            bt, g, c, t = m.bluecoins_type, m.bluecoins_group, m.bluecoins_category, m.bluecoins_title
            for existing_key in list(self.category_map.keys()):
                if existing_key[1] == bt and existing_key[2] == g and \
                   existing_key[3] == c and existing_key[4] == t:
                    if existing_key not in manual_keys:
                        del self.category_map[existing_key]
    
    def _match_owner(self, owner_name):
        """匹配拥有者，返回 Owner 对象或 None"""
        if not owner_name:
            return self.owner
        
        owner_name = owner_name.strip()
        
        if self.family_id:
            stmt = select(Owner).where(Owner.family_id == self.family_id)
            family_owners = db.session.scalars(stmt).all()
            for o in family_owners:
                if o.owner_name.strip() == owner_name:
                    return o
        
        stmt = select(Owner).where(Owner.owner_name == owner_name)
        matched = db.session.scalars(stmt).first()
        if matched:
            return matched
        
        if self.family_id:
            family = db.session.get(Family, self.family_id)
            if family and family.family_name.strip() == owner_name:
                stmt = select(Owner).where(
                    Owner.family_id == self.family_id,
                    Owner.owner_name == family.family_name
                )
                family_owner = db.session.scalars(stmt).first()
                if not family_owner:
                    family_owner = Owner(
                        owner_name=family.family_name,
                        family_id=self.family_id,
                        user_id=None
                    )
                    db.session.add(family_owner)
                    db.session.flush()
                return family_owner
        
        return None
    
    def import_accounts_csv(self, file_content):
        """导入账户 CSV"""
        reader = csv.DictReader(io.StringIO(file_content), skipinitialspace=True)
        
        seen_ids = set()
        seen_combinations = set()
        
        for row in reader:
            bluecoins_name = row.get('账户', '').strip()
            if not bluecoins_name:
                continue
            
            if bluecoins_name in self.account_map:
                self.results['accounts']['skipped'] += 1
                self.results['accounts']['details'].append({
                    'name': bluecoins_name,
                    'status': 'skipped',
                    'reason': '已存在映射'
                })
                continue
            
            bc_id = row.get('id', '').strip()
            if bc_id and bc_id in seen_ids:
                self.results['accounts']['skipped'] += 1
                self.results['accounts']['details'].append({
                    'name': bluecoins_name,
                    'status': 'skipped',
                    'reason': f'id {bc_id} 重复'
                })
                continue
            
            if self._is_empty_account_row(row):
                self.results['accounts']['skipped'] += 1
                self.results['accounts']['details'].append({
                    'name': bluecoins_name,
                    'status': 'skipped',
                    'reason': '账户信息为空'
                })
                continue
            
            try:
                account, combination_key = self._create_account_from_row(row, bluecoins_name)
                
                if account is None:
                    owner_name = row.get('account_owner', '').strip()
                    self.results['accounts']['failed'] += 1
                    self.results['accounts']['details'].append({
                        'name': bluecoins_name,
                        'status': 'failed',
                        'reason': f'无法匹配账户拥有者: {owner_name}'
                    })
                    continue
                
                if combination_key in seen_combinations:
                    mapping = BluecoinsAccountMapping(
                        bluecoins_name=bluecoins_name,
                        account_id=account.account_id,
                        is_manual=False
                    )
                    db.session.add(mapping)
                    db.session.flush()
                    self.account_map[bluecoins_name] = account.account_id
                    
                    self.results['accounts']['skipped'] += 1
                    self.results['accounts']['details'].append({
                        'name': bluecoins_name,
                        'status': 'skipped',
                        'reason': '与已有账户重复'
                    })
                    
                    if bc_id:
                        seen_ids.add(bc_id)
                    continue
                
                mapping = BluecoinsAccountMapping(
                    bluecoins_name=bluecoins_name,
                    account_id=account.account_id,
                    is_manual=False
                )
                db.session.add(mapping)
                self.account_map[bluecoins_name] = account.account_id
                self.new_account_mappings[bluecoins_name] = account.account_id
                seen_combinations.add(combination_key)
                
                if bc_id:
                    seen_ids.add(bc_id)
                
                self.results['accounts']['success'] += 1
                self.results['accounts']['details'].append({
                    'name': bluecoins_name,
                    'status': 'success',
                    'account_name': account.account_name
                })
                
            except Exception as e:
                db.session.rollback()
                self.results['accounts']['failed'] += 1
                self.results['accounts']['details'].append({
                    'name': bluecoins_name,
                    'status': 'failed',
                    'reason': str(e)
                })
        
        db.session.commit()
        return self.results['accounts']
    
    def _is_empty_account_row(self, row):
        """检查账户行是否除账户名外所有映射字段为空"""
        name = row.get('account_name', '').strip()
        atype = row.get('account_type', '').strip()
        custodian = row.get('account_custodian', '').strip()
        currency = row.get('account_currency_name', '').strip()
        owner = row.get('account_owner', '').strip()
        return not any([name, atype, custodian, currency, owner])
    
    def _create_account_from_row(self, row, bluecoins_name):
        """从 CSV 行创建账户，返回 (account, combination_key)"""
        account_name = row.get('account_name', bluecoins_name).strip()
        account_other_name = row.get('account_other_name', '').strip() or None
        account_type_str = row.get('account_type', 'SAVING').strip()
        account_custodian = row.get('account_custodian', '').strip()
        account_currency = row.get('account_currency_name', 'HKD').strip()
        owner_name = row.get('account_owner', '').strip()
        account_isin = row.get('account_isin', '').strip().upper() or None
        
        create_date = self._parse_date(row.get('account_create_date', ''))
        if create_date is None:
            create_date = datetime.now(timezone.utc).date()
        
        close_date = self._parse_date(row.get('account_close_date', ''))
        
        try:
            account_type = AccountType[account_type_str]
        except KeyError:
            account_type = AccountType.SAVING
        
        owner = self._match_owner(owner_name if owner_name else None)
        if not owner:
            return None, None
        
        ao_name = account_other_name or ''
        
        combination_key = (
            account_name, ao_name, account_type,
            account_custodian, account_currency, owner.owner_id
        )
        
        # 检查是否已存在相同账户
        stmt = select(Account).where(
            Account.account_name == account_name,
            Account.account_type == account_type,
            Account.account_custodian == account_custodian,
            Account.account_currency_name == account_currency,
            Account.account_owner_id == owner.owner_id
        )
        existing = db.session.scalars(stmt).first()
        
        if existing:
            # existing._existing = True
            return existing, combination_key
        
        account = Account(
            account_name=account_name,
            account_other_name=account_other_name,
            account_type=account_type,
            account_create_date=create_date,
            account_close_date=close_date,
            account_custodian=account_custodian,
            account_currency_name=account_currency,
            account_owner_id=owner.owner_id,
            account_isin=account_isin
        )
        db.session.add(account)
        db.session.flush()
        return account, combination_key
    
    def import_categories_csv(self, file_content):
        """导入分类 CSV"""
        reader = csv.DictReader(io.StringIO(file_content), skipinitialspace=True)
        
        seen_combinations = set()
        
        for row in reader:
            year = row.get('年份', '').strip()
            bc_type = row.get('类型', '').strip()
            group = row.get('类别分组名称', '').strip()
            category_name = row.get('类别', '').strip()
            title = row.get('标题', '').strip()
            
            if not all([year, bc_type, group, category_name, title]):
                continue
            
            key = (year, bc_type, group, category_name, title)
            
            if key in self.category_map:
                self.results['categories']['skipped'] += 1
                self.results['categories']['details'].append({
                    'name': f'{group}/{category_name}/{title}',
                    'status': 'skipped',
                    'reason': '已存在映射'
                })
                continue
            
            if self._is_empty_category_row(row):
                self.results['categories']['skipped'] += 1
                self.results['categories']['details'].append({
                    'name': f'{group}/{category_name}/{title}',
                    'status': 'skipped',
                    'reason': '分类信息为空'
                })
                continue
            
            try:
                cat, combination_key = self._create_category_from_row(row, key)
                
                if combination_key in seen_combinations:
                    mapping = BluecoinsCategoryMapping(
                        bluecoins_year=year,
                        bluecoins_type=bc_type,
                        bluecoins_group=group,
                        bluecoins_category=category_name,
                        bluecoins_title=title,
                        category_id=cat.category_id,
                        is_manual=False
                    )
                    db.session.add(mapping)
                    db.session.flush()
                    self.category_map[key] = cat.category_id
                    
                    self.results['categories']['skipped'] += 1
                    self.results['categories']['details'].append({
                        'name': f'{group}/{category_name}/{title}',
                        'status': 'skipped',
                        'reason': '与已有分类重复'
                    })
                    continue
                
                mapping = BluecoinsCategoryMapping(
                    bluecoins_year=year,
                    bluecoins_type=bc_type,
                    bluecoins_group=group,
                    bluecoins_category=category_name,
                    bluecoins_title=title,
                    category_id=cat.category_id,
                    is_manual=False
                )
                db.session.add(mapping)
                
                self.category_map[key] = cat.category_id
                self.new_category_mappings[key] = cat.category_id
                seen_combinations.add(combination_key)
                
                self.results['categories']['success'] += 1
                self.results['categories']['details'].append({
                    'name': f'{group}/{category_name}/{title}',
                    'status': 'success',
                    'category_name': cat.category_name
                })
            except Exception as e:
                db.session.rollback()
                self.results['categories']['failed'] += 1
                self.results['categories']['details'].append({
                    'name': f'{group}/{category_name}/{title}',
                    'status': 'failed',
                    'reason': str(e)
                })
        
        db.session.commit()
        return self.results['categories']
    
    def _is_empty_category_row(self, row):
        """检查分类行是否除映射字段外所有数据库字段为空"""
        name = row.get('category_name', '').strip()
        cls = row.get('category_class', '').strip()
        subclass = row.get('category_subclass', '').strip()
        ctype = row.get('category_type', '').strip()
        return not any([name, cls, subclass, ctype])
    
    def _create_category_from_row(self, row, key):
        """从 CSV 行创建分类，返回 (category, combination_key)"""
        year, bc_type, group, category_name, title = key
        
        category_name_val = row.get('category_name', title).strip()
        category_other_name = row.get('category_other_name', '').strip() or None
        category_class = row.get('category_class', group).strip()
        category_subclass = row.get('category_subclass', category_name).strip()
        category_type_str = row.get('category_type', 'E').strip()
        
        if category_type_str in ('I', 'E', 'T', 'S'):
            category_type = CategoryType(category_type_str)
        elif bc_type == '收入':
            category_type = CategoryType.INCOME
        elif bc_type == '支出':
            category_type = CategoryType.EXPENSE
        elif '转账' in bc_type:
            category_type = CategoryType.TRANSFER
        else:
            category_type = CategoryType.EXPENSE
        
        combination_key = (
            category_name_val,
            category_other_name or '',
            category_class,
            category_subclass,
            category_type
        )
        
        # 检查是否已存在
        stmt = select(Category).where(
            Category.category_name == category_name_val,
            Category.category_class == category_class,
            Category.category_subclass == category_subclass,
            Category.category_type == category_type
        )
        existing = db.session.scalars(stmt).first()
        
        if existing:
            return existing, combination_key
        
        cat = Category(
            category_name=category_name_val,
            category_other_name=category_other_name,
            category_class=category_class,
            category_subclass=category_subclass,
            category_type=category_type
        )
        db.session.add(cat)
        db.session.flush()
        return cat, combination_key
    
    def import_transactions_csv(self, file_content, manual_mappings=None, 
                                skipped_accounts=None, skipped_categories=None, dry_run=False):
        """导入交易 CSV"""
        if manual_mappings is None:
            manual_mappings = {'accounts': {}, 'categories': {}}
        if skipped_accounts is None:
            skipped_accounts = set()
        if skipped_categories is None:
            skipped_categories = set()
        
        self._apply_manual_mappings(manual_mappings)
        
        reader = csv.DictReader(io.StringIO(file_content), skipinitialspace=True)
        rows = list(reader)
        
        transfer_pairs = self._find_transfer_pairs(rows)
        
        for i, row in enumerate(rows):
            if row.get('类型', '').strip() == '转账' and i in transfer_pairs.get('processed', set()):
                continue
            
            # 检查是否明确跳过
            bc_account = row.get('账户', '').strip()
            bc_group = row.get('类别分组名称', '').strip()
            bc_category = row.get('类别', '').strip()
            bc_title = row.get('标题', '').strip()
            bc_type = row.get('类型', '').strip()
            
            if bc_account in skipped_accounts:
                self.results['transactions']['skipped'] += 1
                self.results['transactions']['details'].append({
                    'row': i + 1, 'status': 'skipped',
                    'reason': f'用户跳过账户: {bc_account}'
                })
                self.skipped_transactions.append(row)
                continue
            
            trans_year = row.get('日期', '').strip()[:4]
            cat_key_str = f"{trans_year}|||{bc_type}|||{bc_group}|||{bc_category}|||{bc_title}"
            if cat_key_str in skipped_categories:
                self.results['transactions']['skipped'] += 1
                self.results['transactions']['details'].append({
                    'row': i + 1, 'status': 'skipped',
                    'reason': f'用户跳过分类: {bc_group}/{bc_category}/{bc_title}'
                })
                self.skipped_transactions.append(row)
                continue
            
            savepoint = db.session.begin_nested()
            try:
                result = self._import_single_transaction(row, rows, i, transfer_pairs)
                savepoint.commit()
                
                if result == 'success':
                    self.results['transactions']['success'] += 1
                elif result == 'skipped':
                    self.results['transactions']['skipped'] += 1
                    self.skipped_transactions.append(row)
                elif result == 'transfer_pair':
                    self.results['transactions']['success'] += 2
            except Exception as e:
                savepoint.rollback()
                self.results['transactions']['failed'] += 1
                self.results['transactions']['details'].append({
                    'row': i + 1, 'status': 'failed', 'reason': str(e)
                })
        
        if not dry_run:
            db.session.commit()
        return self.results['transactions']
    
    def _apply_manual_mappings(self, manual_mappings):
        """应用手动映射"""
        for bc_name, account_id in manual_mappings.get('accounts', {}).items():
            if bc_name and account_id and bc_name not in self.account_map:
                mapping = BluecoinsAccountMapping(
                    bluecoins_name=bc_name,
                    account_id=int(account_id),
                    is_manual=True
                )
                db.session.add(mapping)
                self.account_map[bc_name] = int(account_id)
        
        for key_str, category_id in manual_mappings.get('categories', {}).items():
            parts = key_str.split('|||')
            if len(parts) == 5 and category_id:
                key = tuple(parts)
                bt, g, c, t = parts[1], parts[2], parts[3], parts[4]
                for existing_key in list(self.category_map.keys()):
                    if existing_key[1] == bt and existing_key[2] == g and \
                       existing_key[3] == c and existing_key[4] == t:
                        del self.category_map[existing_key]
                # 检查现有映射
                stmt = select(BluecoinsCategoryMapping).where(
                    BluecoinsCategoryMapping.bluecoins_year == parts[0],
                    BluecoinsCategoryMapping.bluecoins_type == parts[1],
                    BluecoinsCategoryMapping.bluecoins_group == parts[2],
                    BluecoinsCategoryMapping.bluecoins_category == parts[3],
                    BluecoinsCategoryMapping.bluecoins_title == parts[4]
                )
                existing = db.session.scalars(stmt).first()
                if existing:
                    existing.category_id = int(category_id)
                    existing.is_manual = True
                else:
                    mapping = BluecoinsCategoryMapping(
                        bluecoins_year=parts[0],
                        bluecoins_type=parts[1],
                        bluecoins_group=parts[2],
                        bluecoins_category=parts[3],
                        bluecoins_title=parts[4],
                        category_id=int(category_id),
                        is_manual=True
                    )
                    db.session.add(mapping)
                self.category_map[key] = int(category_id)
        
        db.session.flush()

    def _find_transfer_pairs(self, rows):
        """查找转账配对（相邻、金额一正一负互为相反数）"""
        pairs = {}
        processed = set()
        
        for i in range(len(rows) - 1):
            if rows[i].get('类型', '') == '转账' and rows[i + 1].get('类型', '') == '转账':
                try:
                    amount1 = float(rows[i].get('金额', 0))
                    amount2 = float(rows[i + 1].get('金额', 0))
                    
                    if abs(amount1 + amount2) < 0.01 and amount1 != amount2:
                        pairs[i] = i + 1
                        processed.add(i + 1)
                except (ValueError, TypeError):
                    pass
        
        pairs['processed'] = processed
        return pairs
    
    def _import_single_transaction(self, row, all_rows, index, transfer_pairs):
        """导入单条交易"""
        bc_type = row.get('类型', '').strip()
        bc_account = row.get('账户', '').strip()
        bc_group = row.get('类别分组名称', '').strip()
        bc_category = row.get('类别', '').strip()
        title = row.get('标题', '').strip()
        amount = float(row.get('金额', 0))
        currency = row.get('货币', 'HKD').strip()
        description = row.get('备注', '').strip()
        
        date_str = row.get('日期', '').strip()
        time_str = row.get('设置时间', '').strip()
        trans_datetime = self._parse_datetime(date_str, time_str)
        
        account_id = self._match_account(bc_account)
        if not account_id:
            self.results['transactions']['details'].append({
                'row': index + 1, 'status': 'skipped',
                'reason': f'无法匹配账户: {bc_account}', 'title': title
            })
            return 'skipped'
        
        if bc_type == '转账':
            category_id = self._get_transfer_category_id()
        else:
            category_id = self._match_category(bc_type, bc_group, bc_category, title)
        
        if not category_id:
            self.results['transactions']['details'].append({
                'row': index + 1, 'status': 'skipped',
                'reason': f'无法匹配分类: {bc_group}/{bc_category}/{title}', 'title': title
            })
            return 'skipped'
        
        trans_status = TransactionStatus.UNVERIFIED

        if bc_type == '转账' and index in transfer_pairs:
            return self._import_transfer_pair(
                row, all_rows, index, transfer_pairs,
                category_id, currency, trans_status, trans_datetime, description
            )

        kwargs = {
            'trans_datetime': trans_datetime,
            'trans_desc': description if description else '',
            'trans_account_id': account_id,
            'trans_category_id': category_id,
            'trans_owner_id': self.owner.owner_id,
            'trans_status': trans_status
        }

        is_fx = currency != 'HKD' and bc_type != '转账'

        if is_fx:
            file_rate_str = row.get('汇率', '').strip()
            try:
                file_rate = float(file_rate_str) if file_rate_str else 0.0
            except ValueError:
                file_rate = 0.0

            if file_rate > 0:
                effective_rate = file_rate
                stored_rate = file_rate
            else:
                spot_rate = get_fx_rate_to_hkd(currency, trans_datetime.date())
                effective_rate = 1.0 / spot_rate
                stored_rate = 0.0

            hkd_amount = round(amount / effective_rate, 2)
            kwargs.update({
                'trans_amount': hkd_amount,
                'trans_currency_name': 'HKD',
                'trans_fx_amount': amount,
                'trans_fx_rate': stored_rate,
                'trans_fx_currency_name': currency,
                'trans_is_rhs_currency_ind': True,
            })
        else:
            kwargs.update({
                'trans_amount': amount,
                'trans_currency_name': currency,
            })

        # Read optional unit columns from CSV
        unit_str = row.get('unit', '').strip() or row.get('单位', '').strip()
        unit_price_str = row.get('unit_price', '').strip() or row.get('单位单价', '').strip()
        if not is_fx and (unit_str or unit_price_str):
            try:
                unit_val = float(unit_str) if unit_str else None
                unit_price_val = float(unit_price_str) if unit_price_str else None
                # Validate / auto-fill
                if unit_val is not None and unit_price_val is not None:
                    expected_hkd = round(abs(unit_val) * unit_price_val, 2)
                    actual_hkd = abs(kwargs['trans_amount'])
                    if unit_price_val > 0 and abs(actual_hkd - expected_hkd) > 0.02:
                        raise ValueError(f'单位×单价 ({unit_val} × {unit_price_val} ≈ {expected_hkd}) 与交易金额 ({actual_hkd}) 不符')
                if unit_val is not None and unit_price_val is not None:
                    kwargs['trans_unit'] = unit_val if kwargs['trans_amount'] > 0 else -unit_val
                    kwargs['trans_unit_price'] = unit_price_val
                    kwargs['trans_unit_name'] = None
            except ValueError as e:
                self.results['transactions']['details'].append({
                    'row': index + 1, 'status': 'failed', 'reason': str(e)
                })
                return 'failed'

        transaction = Transaction(**kwargs)
        db.session.add(transaction)
        return 'success'
    
    def _import_transfer_pair(self, row, all_rows, index, transfer_pairs, category_id, currency, trans_status, trans_datetime, description):
        """导入转账配对记录"""
        pair_index = transfer_pairs[index]
        pair_row = all_rows[pair_index]
        amount = float(row.get('金额', 0))
        pair_amount = float(pair_row.get('金额', 0))
        bc_account = row.get('账户', '').strip()
        pair_account = pair_row.get('账户', '').strip()
        
        account_id = self._match_account(bc_account)
        pair_account_id = self._match_account(pair_account)
        
        if not account_id or not pair_account_id:
            return 'skipped'
        
        if amount < 0:
            out_account_id = account_id
            in_account_id = pair_account_id
            out_amount = amount
            in_amount = abs(pair_amount)
        else:
            out_account_id = pair_account_id
            in_account_id = account_id
            out_amount = pair_amount
            in_amount = abs(amount)
        
        trans_out = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=description if description else '',
            trans_amount=out_amount,
            trans_currency_name=currency,
            trans_account_id=out_account_id,
            trans_category_id=category_id,
            trans_owner_id=self.owner.owner_id,
            trans_status=trans_status
        )
        db.session.add(trans_out)
        db.session.flush()
        
        trans_in = Transaction(
            trans_datetime=trans_datetime,
            trans_desc=description if description else '',
            trans_amount=in_amount,
            trans_currency_name=currency,
            trans_account_id=in_account_id,
            trans_category_id=category_id,
            trans_owner_id=self.owner.owner_id,
            trans_counter_id=trans_out.trans_id,
            trans_status=trans_status
        )
        db.session.add(trans_in)
        db.session.flush()
        
        trans_out.trans_counter_id = trans_in.trans_id
        db.session.add(trans_out)
        
        return 'transfer_pair'
    
    def _match_account(self, bluecoins_name):
        """匹配账户，返回 account_id 或 None"""
        if bluecoins_name in self.account_map:
            return self.account_map[bluecoins_name]
        
        if bluecoins_name in self.new_account_mappings:
            return self.new_account_mappings[bluecoins_name]
        
        # 先查当前 owner 的账户
        stmt = select(Account).where(
            Account.account_name == bluecoins_name,
            Account.account_owner_id == self.owner.owner_id
        )
        account = db.session.scalars(stmt).first()
        if not account:
            # 查家庭范围内所有账户
            family_owner_stmt = select(Owner.owner_id).where(Owner.family_id == self.family_id)
            family_owner_ids = db.session.scalars(family_owner_stmt).all()
            stmt = select(Account).where(
                Account.account_name == bluecoins_name,
                Account.account_owner_id.in_(family_owner_ids)
            )
            account = db.session.scalars(stmt).first()
        
        if account:
            mapping = BluecoinsAccountMapping(
                bluecoins_name=bluecoins_name,
                account_id=account.account_id,
                is_manual=False
            )
            db.session.add(mapping)
            db.session.flush()
            self.account_map[bluecoins_name] = account.account_id
            return account.account_id
        
        return None
    
    def _match_category(self, bc_type, group, category_name, title, amount=None):
        """匹配分类，返回 category_id 或 None"""
        for key, cat_id in {**self.category_map, **self.new_category_mappings}.items():
            year, bt, g, c, t = key
            if g == group and c == category_name and t == title and bt == bc_type:
                return cat_id
        
        # 尝试通过 category_name 直接匹配
        stmt = select(Category).where(Category.category_name == title, Category.category_subclass == category_name)
        cat = db.session.scalars(stmt).first()
        if not cat:
            stmt = select(Category).where(Category.category_name == title)
            cat = db.session.scalars(stmt).first()
        
        if cat:
            try:
                key = ('', bc_type, group, category_name, title)
                stmt = select(BluecoinsCategoryMapping).where(
                    BluecoinsCategoryMapping.bluecoins_year == '',
                    BluecoinsCategoryMapping.bluecoins_type == bc_type,
                    BluecoinsCategoryMapping.bluecoins_group == group,
                    BluecoinsCategoryMapping.bluecoins_category == category_name,
                    BluecoinsCategoryMapping.bluecoins_title == title
                )
                existing = db.session.scalars(stmt).first()
                if existing:
                    existing.category_id = cat.category_id
                else:
                    mapping = BluecoinsCategoryMapping(
                        bluecoins_year='', bluecoins_type=bc_type,
                        bluecoins_group=group, bluecoins_category=category_name,
                        bluecoins_title=title, category_id=cat.category_id, is_manual=False
                    )
                    db.session.add(mapping)
                    db.session.flush()
                self.category_map[key] = cat.category_id
                return cat.category_id
            except Exception:
                pass
        
        return None
    
    def _get_transfer_category_id(self):
        """获取或创建转账分类"""
        stmt = select(Category).where(Category.category_type == CategoryType.TRANSFER)
        cat = db.session.scalars(stmt).first()
        if cat:
            return cat.category_id
        
        cat = Category(
            category_name='账户转账', category_class='转账',
            category_subclass='内部转账', category_type=CategoryType.TRANSFER
        )
        db.session.add(cat)
        db.session.flush()
        return cat.category_id
    
    def _parse_datetime(self, date_str, time_str):
        """解析日期时间"""
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            return datetime.strptime(date_str.strip(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                dt = datetime.strptime(date_str.strip(), '%Y-%m-%d')
                if time_str and time_str.strip():
                    try:
                        t = datetime.strptime(time_str.strip(), '%H:%M').time()
                        return datetime.combine(dt, t).replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.now(timezone.utc)
    
    def _parse_date(self, date_str):
        """解析日期，空值返回 None"""
        if not date_str or not date_str.strip():
            return None
        date_str = date_str.strip().strip('"').strip()
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y%m%d').date()
            except ValueError:
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').date()
                except ValueError:
                    return None
    
    def get_skipped_transactions(self):
        """获取跳过的交易列表"""
        result = []
        seen_accounts = set()
        seen_categories = {}
        
        for row in self.skipped_transactions:
            bc_account = row.get('账户', '').strip()
            bc_group = row.get('类别分组名称', '').strip()
            bc_category = row.get('类别', '').strip()
            bc_title = row.get('标题', '').strip()
            bc_type = row.get('类型', '').strip()
            
            account_matched = self._match_account(bc_account) is not None
            category_matched = False
            
            if bc_type != '转账':
                category_matched = self._match_category(
                    bc_type, bc_group, bc_category, bc_title
                ) is not None
            
            reason = []
            if not account_matched:
                reason.append('账户未匹配')
                seen_accounts.add(bc_account)
            if not category_matched and bc_type != '转账':
                reason.append('分类未匹配')
            trans_year = row.get('日期', '').strip()[:4]
            key = (trans_year, bc_type, bc_group, bc_category, bc_title)
            if key not in seen_categories:
                seen_categories[key] = {'accounts': set(), 'bc_type': bc_type, 'group': bc_group,
                                        'category': bc_category, 'title': bc_title}
            seen_categories[key]['accounts'].add(bc_account)
            
            result.append({
                'row': row,
                'reason': ', '.join(reason) if reason else '未知',
                'account': bc_account, 'group': bc_group,
                'category': bc_category, 'title': bc_title,
                'type': bc_type, 'amount': row.get('金额', '0'), 'date': row.get('日期', ''),
            })
        
        missing_categories_list = []
        for key, data in seen_categories.items():
            missing_categories_list.append({
                'key': key, 'bc_type': data['bc_type'], 'group': data['group'],
                'category': data['category'], 'title': data['title'],
                'accounts': list(data['accounts'])
            })
        
        return result, list(seen_accounts), missing_categories_list
    
    def get_skipped_csv(self):
        """生成跳过交易的 CSV"""
        if not self.skipped_transactions:
            return ''
        
        output = io.StringIO()
        fieldnames = ['类型', '日期', '设置时间', '标题', '金额', '货币', '汇率',
                      '类别分组名称', '类别', '账户', '备注', '标签', '状态']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in self.skipped_transactions:
            writer.writerow({k: row.get(k, '') for k in fieldnames})
        
        return output.getvalue()
    
    def get_summary(self):
        """获取导入摘要"""
        return self.results