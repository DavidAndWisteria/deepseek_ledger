import io
import pytest
from app import db
from app.models import (
    Account, Category, Owner, User, Transaction,
    AccountType, CategoryType,
    BluecoinsAccountMapping, BluecoinsCategoryMapping
)
from app.services.import_service import ImportService
from unittest.mock import patch


# ===============================================================
# 测试用 CSV
# ===============================================================

# 交易 CSV 表头（Bluecoins 格式）
TRANSACTION_HEADER = "类型,日期,设置时间,标题,金额,货币,汇率,类别分组名称,类别,账户,备注,标签,状态"

# 单条支出交易
SINGLE_EXPENSE = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,测试银行卡,,,核对
"""

# 单条收入交易
SINGLE_INCOME = f"""{TRANSACTION_HEADER}
收入,2025-06-20 09:00:00,09:00,工资,50000,HKD,1.0,职业,工资,测试银行卡,,,核对
"""

# 多条正常交易（同一账户和分类，测试批量导入）
MULTIPLE_EXPENSES = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-20 12:00:00,12:00,午餐,-120,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-21 12:00:00,12:00,午餐,-90,HKD,1.0,日常,餐饮,测试银行卡,,,核对
"""

# 含坏数据的交易（第二行金额格式错误）
BAD_AMOUNT_ROW = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-20 12:00:00,12:00,午餐,N/A,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-21 12:00:00,12:00,午餐,-90,HKD,1.0,日常,餐饮,测试银行卡,,,核对
"""

# 不同账户的行
MULTIPLE_ACCOUNTS = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-20 12:00:00,12:00,购物,-200,HKD,1.0,购物,零售,测试银行卡,,,核对
"""

# 完整不匹配的行（无对应账户和分类）
UNMATCHED_ALL = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,神秘交易,-50,HKD,1.0,未知分组,未知类别,不存在的账户,,,核对
"""

# 部分不匹配
PARTIAL_UNMATCHED = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,测试银行卡,,,核对
支出,2025-06-20 12:00:00,12:00,神秘交易,-50,HKD,1.0,未知分组,未知类别,不存在的账户,,,核对
支出,2025-06-21 12:00:00,12:00,午餐,-90,HKD,1.0,日常,餐饮,测试银行卡,,,核对
"""

# 转账配对
TRANSFER_PAIR = f"""{TRANSACTION_HEADER}
转账,2025-06-19 12:00:00,12:00,转账记录,-1000,HKD,1.0,转账,转账,测试银行卡,,,核对
转账,2025-06-19 12:00:00,12:00,转账记录,1000,HKD,1.0,转账,转账,储蓄账户,,,核对
"""

# 外汇交易
FX_TRANSACTION = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,购物,-50,USD,7.8,购物,零售,测试银行卡,,,核对
"""

# CSV 只有表头无数据
HEADER_ONLY = TRANSACTION_HEADER

# 格式错误的 CSV
MALFORMED_CSV = "not,a,valid,csv\n1,2,3,4,5,6,7,8,9,10,11,12,13"


# ===============================================================
# 辅助函数
# ===============================================================

def count_transactions():
    return Transaction.query.count()


def count_account_mappings():
    return BluecoinsAccountMapping.query.count()


def count_category_mappings():
    return BluecoinsCategoryMapping.query.count()


def setup_accounts_and_categories(app, test_owner):
    """创建测试用的账户和分类"""
    with app.app_context():
        test_owner_id = test_owner

        # 创建两个账户
        acc1 = Account(
            account_name='测试银行卡',
            account_type=AccountType.SAVING,
            account_custodian='测试银行',
            account_currency_name='HKD',
            account_owner_id=test_owner_id
        )
        acc2 = Account(
            account_name='储蓄账户',
            account_type=AccountType.SAVING,
            account_custodian='另一银行',
            account_currency_name='HKD',
            account_owner_id=test_owner_id
        )
        db.session.add_all([acc1, acc2])
        db.session.flush()

        # 创建分类
        cat1 = Category(
            category_name='午餐',
            category_class='日常',
            category_subclass='餐饮',
            category_type=CategoryType.EXPENSE
        )
        cat2 = Category(
            category_name='工资',
            category_class='职业',
            category_subclass='主业',
            category_type=CategoryType.INCOME
        )
        cat3 = Category(
            category_name='购物',
            category_class='购物',
            category_subclass='零售',
            category_type=CategoryType.EXPENSE
        )
        db.session.add_all([cat1, cat2, cat3])
        db.session.commit()

        return {
            'account1_id': acc1.account_id,
            'account2_id': acc2.account_id,
            'cat1_id': cat1.category_id,
            'cat2_id': cat2.category_id,
            'cat3_id': cat3.category_id,
        }


# ===============================================================
# 测试类
# ===============================================================

class TestImportTransactionsService:
    """交易导入 Service 层测试"""

    def test_basic_import_single_expense(self, app, test_user, test_owner):
        """基本导入：单条支出交易成功"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(SINGLE_EXPENSE)

            assert result['success'] == 1
            assert result['skipped'] == 0
            assert result['failed'] == 0

            txn = Transaction.query.first()
            assert txn is not None
            assert txn.trans_amount == -100
            assert txn.trans_account_id == ids['account1_id']
            assert txn.trans_category_id == ids['cat1_id']
            assert txn.trans_desc == ''
            assert txn.trans_currency_name == 'HKD'

    def test_basic_import_multiple_expenses(self, app, test_user, test_owner):
        """批量导入：多条交易全部成功"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(MULTIPLE_EXPENSES)

            assert result['success'] == 3
            assert result['skipped'] == 0
            assert result['failed'] == 0

            assert count_transactions() == 3

    def test_import_income(self, app, test_user, test_owner):
        """导入收入交易"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(SINGLE_INCOME)

            assert result['success'] == 1
            txn = Transaction.query.first()
            assert txn.trans_amount == 50000
            assert txn.trans_category_id == ids['cat2_id']

    def test_import_all_skipped_no_accounts(self, app, test_user):
        """没有账户和分类时，全部跳过"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(SINGLE_EXPENSE)

            assert result['success'] == 0
            assert result['skipped'] == 1
            assert result['failed'] == 0
            assert count_transactions() == 0

    def test_import_partial_unmatched(self, app, test_user, test_owner):
        """部分匹配、部分跳过"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(PARTIAL_UNMATCHED)

            assert result['success'] == 2
            assert result['skipped'] == 1
            assert result['failed'] == 0
            assert count_transactions() == 2

    def test_preview_dry_run_does_not_persist(self, app, test_user, test_owner):
        """预览模式（dry_run=True）不持久化交易"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            savepoint = db.session.begin_nested()
            result = service.import_transactions_csv(SINGLE_EXPENSE, dry_run=True)
            savepoint.rollback()

            assert result['success'] == 1
            assert count_transactions() == 0

    def test_preview_does_not_persist_mappings(self, app, test_user, test_owner):
        """预览模式不持久化自动创建的映射"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            savepoint = db.session.begin_nested()
            result = service.import_transactions_csv(MULTIPLE_EXPENSES, dry_run=True)
            savepoint.rollback()

            assert result['success'] == 3
            assert count_account_mappings() == 0
            assert count_category_mappings() == 0

    def test_savepoint_isolation_bad_row(self, app, test_user, test_owner):
        """单行异常不撤销其他行（savepoint 隔离）——核心修复验证"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(BAD_AMOUNT_ROW)

            # 第2行 bad amount 应失败，但不影响第1行和第3行
            assert result['success'] == 2
            assert result['failed'] == 1
            assert result['skipped'] == 0
            assert count_transactions() == 2

    def test_savepoint_isolation_leaves_mappings_intact(self, app, test_user, test_owner):
        """失败行的 savepoint 回滚不影响好的映射"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(BAD_AMOUNT_ROW)

            # 好的行照常创建了映射
            assert count_account_mappings() == 1  # 测试银行卡
            assert count_category_mappings() == 1  # 午餐

    def test_import_with_manual_account_mapping(self, app, test_user, test_owner):
        """手动映射账户"""
        ids = setup_accounts_and_categories(app, test_owner)
        csv_with_custom_account = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,午餐,-100,HKD,1.0,日常,餐饮,CustomBank,,,核对
"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            manual_mappings = {
                'accounts': {'CustomBank': str(ids['account1_id'])},
                'categories': {}
            }
            result = service.import_transactions_csv(
                csv_with_custom_account, manual_mappings=manual_mappings
            )

            assert result['success'] == 1
            txn = Transaction.query.first()
            assert txn.trans_account_id == ids['account1_id']

    def test_import_with_manual_category_mapping(self, app, test_user, test_owner):
        """手动映射分类"""
        ids = setup_accounts_and_categories(app, test_owner)
        csv_with_custom_cat = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,自定义标题,-100,HKD,1.0,CustomGroup,CustomCat,测试银行卡,,,核对
"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            manual_mappings = {
                'accounts': {},
                'categories': {'|||支出|||CustomGroup|||CustomCat|||自定义标题': str(ids['cat1_id'])}
            }
            result = service.import_transactions_csv(
                csv_with_custom_cat, manual_mappings=manual_mappings
            )

            assert result['success'] == 1
            txn = Transaction.query.first()
            assert txn.trans_category_id == ids['cat1_id']

    def test_import_skip_account(self, app, test_user, test_owner):
        """指定跳过的账户"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(
                SINGLE_EXPENSE, skipped_accounts={'测试银行卡'}
            )

            assert result['success'] == 0
            assert result['skipped'] == 1
            assert count_transactions() == 0

    def test_import_skip_category(self, app, test_user, test_owner):
        """指定跳过的分类"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            # 分类跳过 key 格式: year|||type|||group|||category|||title
            skip_key = "2025|||支出|||日常|||餐饮|||午餐"
            result = service.import_transactions_csv(
                SINGLE_EXPENSE, skipped_categories={skip_key}
            )

            assert result['success'] == 0
            assert result['skipped'] == 1
            assert count_transactions() == 0

    def test_import_multiple_accounts(self, app, test_user, test_owner):
        """同一 CSV 中使用不同账户"""
        ids = setup_accounts_and_categories(app, test_owner)
        csv_content = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,购物,-200,HKD,1.0,购物,零售,测试银行卡,,,核对
支出,2025-06-20 12:00:00,12:00,午餐,-50,HKD,1.0,日常,餐饮,储蓄账户,,,核对
"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(csv_content)

            assert result['success'] == 2

    def test_import_empty_csv(self, app, test_user):
        """空 CSV 不报错"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv('')

            assert result['success'] == 0
            assert result['failed'] == 0
            assert result['skipped'] == 0

    def test_import_header_only(self, app, test_user):
        """仅表头的 CSV 不报错"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(HEADER_ONLY)

            assert result['success'] == 0
            assert result['failed'] == 0
            assert result['skipped'] == 0

    def test_import_creates_mappings_automatically(self, app, test_user, test_owner):
        """首次导入自动创建账户和分类映射"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(SINGLE_EXPENSE)

            # 账户映射
            acct_map = BluecoinsAccountMapping.query.filter_by(
                bluecoins_name='测试银行卡'
            ).first()
            assert acct_map is not None
            assert acct_map.account_id == ids['account1_id']
            assert acct_map.is_manual is False

            # 分类映射
            cat_map = BluecoinsCategoryMapping.query.filter_by(
                bluecoins_type='支出',
                bluecoins_group='日常',
                bluecoins_category='餐饮',
                bluecoins_title='午餐'
            ).first()
            assert cat_map is not None
            assert cat_map.category_id == ids['cat1_id']

    def test_reimport_uses_existing_mappings(self, app, test_user, test_owner):
        """第二次导入时复用已有映射"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service1 = ImportService(user)
            service1.import_transactions_csv(SINGLE_EXPENSE)

            # 第二次导入同一 CSV
            service2 = ImportService(user)
            result = service2.import_transactions_csv(SINGLE_EXPENSE)

            assert result['success'] == 1
            # 映射不应重复创建
            assert count_account_mappings() == 1
            assert count_category_mappings() == 1
            assert count_transactions() == 2

    def test_get_skipped_transactions(self, app, test_user):
        """获取跳过的交易列表"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(UNMATCHED_ALL, dry_run=True)

            skipped, missing_accounts, missing_categories = service.get_skipped_transactions()

            assert len(skipped) == 1
            assert len(missing_accounts) == 1
            assert '不存在的账户' in missing_accounts
            assert len(missing_categories) > 0

    def test_get_summary(self, app, test_user, test_owner):
        """获取导入摘要"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(SINGLE_EXPENSE)

            summary = service.get_summary()
            assert summary['transactions']['success'] == 1
            assert 'accounts' in summary
            assert 'categories' in summary

    def test_import_transfer_pair(self, app, test_user, test_owner):
        """导入转账配对"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(TRANSFER_PAIR)

            assert result['success'] == 2  # transfer_pair counts as 2 successes
            assert result['failed'] == 0

            txns = Transaction.query.all()
            assert len(txns) == 2
            # 两个交易应互为 counter
            t1, t2 = txns
            assert t1.trans_counter_id == t2.trans_id
            assert t2.trans_counter_id == t1.trans_id
            # 一正一负
            assert t1.trans_amount < 0 or t2.trans_amount < 0
            assert t1.trans_amount > 0 or t2.trans_amount > 0

    def test_import_fx_transaction(self, app, test_user, test_owner):
        """导入外币交易（含汇率转换）"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(FX_TRANSACTION)

            assert result['success'] == 1
            txn = Transaction.query.first()
            assert txn.trans_fx_currency_name == 'USD'
            assert txn.trans_fx_amount == -50

    def test_import_fx_no_rate_fallback(self, app, test_user, test_owner):
        """外币交易无汇率时走 fallback"""
        ids = setup_accounts_and_categories(app, test_owner)
        csv_no_rate = f"""{TRANSACTION_HEADER}
支出,2025-06-19 12:00:00,12:00,购物,-50,USD,,购物,零售,测试银行卡,,,核对
"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            # FX fallback 时可能需要外部 API，mock 掉以避免网络调用
            with patch('app.services.import_service.get_fx_rate_to_hkd', return_value=7.8):
                result = service.import_transactions_csv(csv_no_rate)

            assert result['success'] == 1
            txn = Transaction.query.first()
            assert txn.trans_fx_currency_name == 'USD'
            # 应使用 fallback 汇率
            assert txn.trans_fx_rate == 0.0  # fallback sets stored_rate=0.0

    def test_transaction_status_default_unverified(self, app, test_user, test_owner):
        """导入的交易状态默认为 UNVERIFIED"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            from app.models import TransactionStatus
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(SINGLE_EXPENSE)

            txn = Transaction.query.first()
            assert txn.trans_status == TransactionStatus.UNVERIFIED

    def test_transfer_pair_has_transfer_category(self, app, test_user, test_owner):
        """转账配对使用转账分类"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(TRANSFER_PAIR)

            txns = Transaction.query.all()
            for txn in txns:
                cat = db.session.get(Category, txn.trans_category_id)
                assert cat.category_type == CategoryType.TRANSFER

    def test_result_details_on_failure(self, app, test_user, test_owner):
        """失败行记录详细信息"""
        ids = setup_accounts_and_categories(app, test_owner)
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_transactions_csv(BAD_AMOUNT_ROW)

            assert result['failed'] == 1
            assert len(result['details']) == 1
            assert result['details'][0]['status'] == 'failed'
            assert 'reason' in result['details'][0]

    def test_get_skipped_csv_generates_export(self, app, test_user):
        """跳过交易可导出 CSV"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_transactions_csv(UNMATCHED_ALL, dry_run=True)

            csv_content = service.get_skipped_csv()
            assert csv_content is not None
            assert len(csv_content) > 0
            assert '账户' in csv_content  # 包含 CSV 头


class TestImportTransactionsRoutes:
    """交易导入路由层测试"""

    def test_upload_preview_route(self, logged_in_client, app, test_owner):
        """上传交易预览返回 200"""
        setup_accounts_and_categories(app, test_owner)
        data = {'file': (io.BytesIO(SINGLE_EXPENSE.encode('utf-8-sig')), 'transactions.csv')}
        resp = logged_in_client.post(
            '/import/transactions/upload',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        # 应包含"导入预览"
        assert '导入预览' in resp.data.decode('utf-8')

    def test_upload_preview_with_skipped_shows_mapping(self, logged_in_client, app, test_owner):
        """上传有未匹配行时显示映射表单"""
        setup_accounts_and_categories(app, test_owner)
        data = {'file': (io.BytesIO(PARTIAL_UNMATCHED.encode('utf-8-sig')), 'transactions.csv')}
        resp = logged_in_client.post(
            '/import/transactions/upload',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '手动处理跳过' in html or '手动映射' in html

    def test_upload_preview_all_matched_shows_confirm(self, logged_in_client, app, test_owner):
        """上传全部匹配时显示确认导入按钮（已修复的模板）"""
        setup_accounts_and_categories(app, test_owner)
        data = {'file': (io.BytesIO(SINGLE_EXPENSE.encode('utf-8-sig')), 'transactions.csv')}
        resp = logged_in_client.post(
            '/import/transactions/upload',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        # 应包含确认表单或全部已匹配字样
        assert '全部交易已成功匹配' in html or '确认导入' in html

    def test_confirm_without_upload_redirects(self, logged_in_client):
        """未上传直接确认应重定向"""
        resp = logged_in_client.post(
            '/import/transactions/confirm',
            data={},
            follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '请先上传文件' in html

    def test_confirm_imports_transactions(self, logged_in_client, app, test_owner):
        """确认导入实际写入交易"""
        setup_accounts_and_categories(app, test_owner)

        # Step 1: 上传预览
        upload_data = {
            'file': (io.BytesIO(SINGLE_EXPENSE.encode('utf-8-sig')), 'transactions.csv')
        }
        upload_resp = logged_in_client.post(
            '/import/transactions/upload',
            data=upload_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert upload_resp.status_code == 200

        # Step 2: 确认导入
        confirm_resp = logged_in_client.post(
            '/import/transactions/confirm',
            data={},
            follow_redirects=True
        )
        assert confirm_resp.status_code == 200

        # 验证交易已写入
        with app.app_context():
            assert count_transactions() == 1

    def test_confirm_with_skip_unmatched(self, logged_in_client, app, test_owner):
        """仅导入已匹配的"""
        setup_accounts_and_categories(app, test_owner)

        # 上传含未匹配行的 CSV
        upload_data = {
            'file': (io.BytesIO(PARTIAL_UNMATCHED.encode('utf-8-sig')), 'transactions.csv')
        }
        logged_in_client.post(
            '/import/transactions/upload',
            data=upload_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        # 确认（skip_unmatched=1）
        confirm_resp = logged_in_client.post(
            '/import/transactions/confirm',
            data={'skip_unmatched': '1'},
            follow_redirects=True
        )
        assert confirm_resp.status_code == 200

        with app.app_context():
            # 只导入已匹配的行
            assert count_transactions() == 2

    def test_confirm_no_file_redirects(self, logged_in_client):
        """无文件时确认重定向"""
        resp = logged_in_client.post(
            '/import/transactions/confirm',
            data={},
            follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '请先上传文件' in html

    def test_import_page_accessible(self, logged_in_client):
        """导入页面可访问"""
        resp = logged_in_client.get('/import')
        assert resp.status_code == 200
        assert '导入' in resp.data.decode('utf-8')

    def test_upload_empty_filename_redirects(self, logged_in_client):
        """上传空文件名重定向"""
        data = {'file': (io.BytesIO(b''), '')}
        resp = logged_in_client.post(
            '/import/transactions/upload',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert '请选择文件' in resp.data.decode('utf-8')

    def test_upload_no_file_redirects(self, logged_in_client):
        """未选择文件重定向"""
        resp = logged_in_client.post(
            '/import/transactions/upload',
            data={},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert '请选择文件' in resp.data.decode('utf-8')

    def test_confirm_from_all_matched_preview(self, logged_in_client, app, test_owner):
        """全部匹配预览后确认导入——验证模板修复"""
        setup_accounts_and_categories(app, test_owner)

        # Step 1: 上传（全部匹配）
        upload_data = {
            'file': (io.BytesIO(SINGLE_EXPENSE.encode('utf-8-sig')), 'transactions.csv')
        }
        upload_resp = logged_in_client.post(
            '/import/transactions/upload',
            data=upload_data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        html = upload_resp.data.decode('utf-8')
        # 应能看到确认表单（修复前只有"返回导入页面"链接）
        assert '确认导入' in html or 'confirm_transactions' in html

        # Step 2: 确认
        confirm_resp = logged_in_client.post(
            '/import/transactions/confirm',
            data={},
            follow_redirects=True
        )
        assert confirm_resp.status_code == 200

        # Step 3: 验证交易已写入
        with app.app_context():
            assert count_transactions() == 1
