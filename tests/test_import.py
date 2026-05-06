import csv
import io
import pytest
from app import db
from app.models import (
    Account, Category, Transaction, Owner, User,
    AccountType, CategoryType, TransactionStatus,
    BluecoinsAccountMapping, BluecoinsCategoryMapping
)
from app.services.import_service import ImportService


# ===============================================================
# 测试用 CSV 数据
# ===============================================================

ACCOUNTS_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Dav - ZA",62,"众安港币活期",,"SAVING",2022-01-24,,"众安银行","HKD","测试用户"
"Dav Master",1,"Dav Master",,"CREDIT_CARD",2021-01-01,,"中信银行","HKD","测试用户"
"Dav - 八达通",2,"八达通",,"CASH",2021-01-01,,"八达通","HKD","测试用户"
"""

EMPTY_ACCOUNT_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"EmptyAcc",99,,,,,,,,
"""

DUPLICATE_ID_ACCOUNT_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Acc1",100,"账户1",,"SAVING",2022-01-01,,"银行1","HKD","测试用户"
"Acc2",100,"账户2",,"SAVING",2022-01-01,,"银行2","HKD","测试用户"
"""

DUPLICATE_COMBO_ACCOUNT_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Acc1",200,"相同账户",,"SAVING",2022-01-01,,"相同银行","HKD","测试用户"
"Acc2",201,"相同账户",,"SAVING",2022-01-01,,"相同银行","HKD","测试用户"
"""

CLOSE_DATE_NONE_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"TestAcc",300,"测试账户",,"SAVING",2022-01-01,,"测试银行","HKD","测试用户"
"""

CATEGORIES_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","日常","交通","上班交通",776.23,50,1,"交通",,"日常","交通","E"
2021,"支出","日常","杂货","惠康",500.00,20,2,"杂货",,"日常","杂货","E"
2021,"收入","投资","基金涨跌","基金涨跌",10000.00,30,3,"基金涨跌",,"投资","基金涨跌","I"
"""

EMPTY_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","日常","交通","上班交通",0,0,10,,,,,,
"""

DUPLICATE_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","日常","交通","交通1",0,0,20,"交通",,"日常","交通","E"
2022,"支出","日常","交通","交通2",0,0,21,"交通",,"日常","交通","E"
"""

TRANSACTIONS_CSV = """类型,日期,设置时间,标题,金额,货币,汇率,类别分组名称,类别,账户,备注,标签,状态
"支出","2026-04-09 18:36:00","18:36","上班交通","-5.90","HKD","1.0000000000","日常","交通","Dav - 八达通","","","核对"
"支出","2026-04-08 19:00:00","19:00","惠康","-29.00","HKD","1.0000000000","日常","杂货","Dav Master","","","核对"
"收入","2026-04-13 10:47:00","10:47","基金涨跌","-9120.09","HKD","1.0000000000","投资","基金涨跌","Dav - ZA","","","核对"
"转账","2026-04-11 21:00:00","21:00","八达通自动增值","500.00","HKD","1.0000000000","(转账)","(转账)","Dav - 八达通","","","核对"
"转账","2026-04-11 21:00:00","21:00","八达通自动增值","-500.00","HKD","1.0000000000","(转账)","(转账)","Dav Master","","","核对"
"""

UNMATCHED_CSV = """类型,日期,设置时间,标题,金额,货币,汇率,类别分组名称,类别,账户,备注,标签,状态
"支出","2026-04-09 18:36:00","18:36","上班交通","-5.90","HKD","1.0000000000","日常","交通","不存在的账户","","","核对"
"""


# ===============================================================
# 映射模型测试
# ===============================================================

class TestBluecoinsMappingModels:
    """映射模型测试"""

    def test_create_account_mapping(self, app, test_owner, test_account):
        """创建账户映射记录"""
        with app.app_context():
            mapping = BluecoinsAccountMapping(
                bluecoins_name='BC-Test-Account',
                account_id=test_account,
                owner_id=test_owner,
                is_manual=False
            )
            db.session.add(mapping)
            db.session.commit()

            assert mapping.mapping_id is not None
            assert mapping.bluecoins_name == 'BC-Test-Account'
            assert mapping.account_id == test_account
            assert mapping.is_manual is False

    def test_create_manual_account_mapping(self, app, test_owner, test_account):
        """创建手动账户映射记录"""
        with app.app_context():
            mapping = BluecoinsAccountMapping(
                bluecoins_name='Manual-Account',
                account_id=test_account,
                owner_id=test_owner,
                is_manual=True
            )
            db.session.add(mapping)
            db.session.commit()

            assert mapping.is_manual is True

    def test_create_category_mapping(self, app, test_category):
        """创建分类映射记录"""
        with app.app_context():
            mapping = BluecoinsCategoryMapping(
                bluecoins_year='2026',
                bluecoins_type='支出',
                bluecoins_group='日常',
                bluecoins_category='交通',
                bluecoins_title='上班交通',
                category_id=test_category,
                is_manual=False
            )
            db.session.add(mapping)
            db.session.commit()

            assert mapping.mapping_id is not None
            assert mapping.category_id == test_category
            assert mapping.bluecoins_group == '日常'

    def test_category_mapping_unique(self, app, test_category):
        """分类映射五元组唯一约束"""
        with app.app_context():
            m1 = BluecoinsCategoryMapping(
                bluecoins_year='2026', bluecoins_type='支出',
                bluecoins_group='日常', bluecoins_category='交通',
                bluecoins_title='上班交通', category_id=test_category
            )
            db.session.add(m1)
            db.session.commit()

            m2 = BluecoinsCategoryMapping(
                bluecoins_year='2026', bluecoins_type='支出',
                bluecoins_group='日常', bluecoins_category='交通',
                bluecoins_title='上班交通', category_id=test_category
            )
            db.session.add(m2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()


# ===============================================================
# 账户导入测试
# ===============================================================

class TestAccountImport:
    """账户导入测试"""

    def test_import_accounts(self, app, test_user):
        """导入账户 CSV"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(ACCOUNTS_CSV)

            assert result['success'] == 3
            assert result['skipped'] == 0
            assert result['failed'] == 0

            # 验证系统账户已创建
            acc = Account.query.filter_by(account_name='众安港币活期').first()
            assert acc is not None
            assert acc.account_type == AccountType.SAVING
            assert acc.account_custodian == '众安银行'

            # 验证映射已创建
            mapping = BluecoinsAccountMapping.query.filter_by(
                bluecoins_name='Dav - ZA'
            ).first()
            assert mapping is not None
            assert mapping.account_id == acc.account_id

    def test_import_accounts_skip_existing(self, app, test_user):
        """重复导入跳过已有映射"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            # 第一次导入
            service.import_accounts_csv(ACCOUNTS_CSV)
            # 第二次导入
            result = service.import_accounts_csv(ACCOUNTS_CSV)

            assert result['skipped'] == 3
            assert result['success'] == 0

    def test_import_accounts_skip_empty_row(self, app, test_user):
        """跳过所有映射字段为空的行"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(EMPTY_ACCOUNT_CSV)

            assert result['skipped'] == 1
            assert result['success'] == 0

    def test_import_accounts_skip_duplicate_id(self, app, test_user):
        """跳过 id 重复的账户"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(DUPLICATE_ID_ACCOUNT_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1

    def test_import_accounts_skip_duplicate_combination(self, app, test_user):
        """跳过完全重复的账户组合"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(DUPLICATE_COMBO_ACCOUNT_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1

    def test_account_close_date_none(self, app, test_user):
        """导入账户时 close_date 为空则保持 None"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(CLOSE_DATE_NONE_CSV)

            acc = Account.query.filter_by(account_name='测试账户').first()
            assert acc is not None
            assert acc.account_close_date is None


# ===============================================================
# 分类导入测试
# ===============================================================

class TestCategoryImport:
    """分类导入测试"""

    def test_import_categories(self, app, test_user):
        """导入分类 CSV"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(CATEGORIES_CSV)

            assert result['success'] == 3
            assert result['skipped'] == 0

            # 验证系统分类已创建
            cat = Category.query.filter_by(category_name='交通').first()
            assert cat is not None
            assert cat.category_type == CategoryType.EXPENSE
            assert cat.category_class == '日常'

            # 验证映射已创建
            mapping = BluecoinsCategoryMapping.query.filter_by(
                bluecoins_group='日常',
                bluecoins_category='交通',
                bluecoins_title='上班交通'
            ).first()
            assert mapping is not None
            assert mapping.category_id == cat.category_id

    def test_import_categories_skip_existing(self, app, test_user):
        """重复导入跳过已有映射"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(CATEGORIES_CSV)
            result = service.import_categories_csv(CATEGORIES_CSV)

            assert result['skipped'] == 3
            assert result['success'] == 0

    def test_import_categories_skip_empty_row(self, app, test_user):
        """跳过所有分类字段为空的行"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(EMPTY_CATEGORY_CSV)

            assert result['skipped'] == 1
            assert result['success'] == 0

    def test_import_categories_skip_duplicate_combination(self, app, test_user):
        """跳过完全重复的分类组合"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(DUPLICATE_CATEGORY_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1


# ===============================================================
# 交易导入测试
# ===============================================================

class TestTransactionImport:
    """交易导入测试"""

    def test_import_transactions_with_mappings(self, app, test_user):
        """导入交易（已建立账户和分类映射）"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            # 先导入账户和分类
            service.import_accounts_csv(ACCOUNTS_CSV)
            service.import_categories_csv(CATEGORIES_CSV)

            # 导入交易
            result = service.import_transactions_csv(TRANSACTIONS_CSV)

            # 5 行交易：2 支出 + 1 收入 + 2 转账(1对)
            assert result['success'] == 5
            assert result['skipped'] == 0

            # 验证交易已创建
            transactions = Transaction.query.all()
            assert len(transactions) == 5

            # 验证支出交易
            expense = Transaction.query.filter_by(trans_desc='上班交通').first()
            assert expense is not None
            assert expense.trans_amount == -5.90
            assert expense.trans_status == TransactionStatus.VERIFIED

    def test_import_transactions_transfer_pair(self, app, test_user):
        """导入转账交易产生配对记录"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)
            service.import_categories_csv(CATEGORIES_CSV)
            service.import_transactions_csv(TRANSACTIONS_CSV)

            transfers = Transaction.query.filter(
                Transaction.trans_desc.contains('八达通自动增值')
            ).all()
            assert len(transfers) == 2

            t1 = transfers[0]
            t2 = transfers[1]
            assert t1.trans_counter_id == t2.trans_id
            assert t2.trans_counter_id == t1.trans_id
            assert t1.trans_amount + t2.trans_amount == 0

    def test_import_transactions_status_mapping(self, app, test_user):
        """导入交易状态映射（核对→VERIFIED）"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)
            service.import_categories_csv(CATEGORIES_CSV)
            service.import_transactions_csv(TRANSACTIONS_CSV)

            transactions = Transaction.query.all()
            for t in transactions:
                assert t.trans_status == TransactionStatus.VERIFIED

    def test_import_transactions_skipped_csv(self, app, test_user):
        """跳过交易可导出 CSV"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(CATEGORIES_CSV)
            result = service.import_transactions_csv(UNMATCHED_CSV)

            assert result['skipped'] == 1

            csv_content = service.get_skipped_csv()
            assert '不存在的账户' in csv_content


# ===============================================================
# 边界测试
# ===============================================================

class TestImportServiceEdgeCases:
    """导入服务边界测试"""

    def test_empty_csv(self, app, test_user):
        """空 CSV 文件"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv('')

            assert result['success'] == 0
            assert result['failed'] == 0

    def test_malformed_csv(self, app, test_user):
        """格式错误的 CSV"""
        bad_csv = 'not,a,csv\n1,2,3'
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(bad_csv)

            assert result['success'] == 0

    def test_parse_date_formats(self, app, test_user):
        """日期格式解析"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            # YYYY-MM-DD
            d = service._parse_date('2026-01-15')
            assert d.year == 2026 and d.month == 1 and d.day == 15

            # YYYYMMDD
            d = service._parse_date('20260115')
            assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_parse_date_empty(self, app, test_user):
        """空日期返回 None"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            assert service._parse_date('') is None
            assert service._parse_date('   ') is None

    def test_parse_datetime_formats(self, app, test_user):
        """日期时间格式解析"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            dt = service._parse_datetime('2026-04-15', '14:32')
            assert dt.year == 2026 and dt.month == 4 and dt.day == 15
            assert dt.hour == 14 and dt.minute == 32

            dt = service._parse_datetime('2026-04-15', '')
            assert dt.hour == 0 and dt.minute == 0

    def test_find_transfer_pairs(self, app, test_user):
        """查找转账配对（相邻、金额相反）"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            rows = [
                {'类型': '转账', '金额': '-500.00'},
                {'类型': '转账', '金额': '500.00'},
                {'类型': '支出', '金额': '-100.00'},
            ]
            pairs = service._find_transfer_pairs(rows)
            assert 0 in pairs
            assert pairs[0] == 1

    def test_find_transfer_pairs_non_adjacent(self, app, test_user):
        """非相邻转账不配对"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)

            rows = [
                {'类型': '转账', '金额': '-500.00'},
                {'类型': '支出', '金额': '-100.00'},
                {'类型': '转账', '金额': '500.00'},
            ]
            pairs = service._find_transfer_pairs(rows)
            assert 0 not in pairs

    def test_get_summary(self, app, test_user):
        """获取导入摘要"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            summary = service.get_summary()

            assert 'accounts' in summary
            assert 'categories' in summary
            assert 'transactions' in summary
            assert summary['accounts']['success'] == 0


# ===============================================================
# 路由测试
# ===============================================================

class TestImportRoutes:
    """导入路由测试"""

    def test_import_page(self, logged_in_client):
        """导入页面加载"""
        response = logged_in_client.get('/import')
        assert response.status_code == 200
        assert '导入' in response.data.decode('utf-8')

    def test_import_accounts_route(self, logged_in_client, app):
        """通过路由导入账户"""
        data = {'file': (io.BytesIO(ACCOUNTS_CSV.encode('utf-8')), 'accounts.csv')}
        response = logged_in_client.post(
            '/import/accounts',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert response.status_code == 200
        assert '导入完成' in response.data.decode('utf-8')

    def test_import_categories_route(self, logged_in_client, app):
        """通过路由导入分类"""
        data = {'file': (io.BytesIO(CATEGORIES_CSV.encode('utf-8')), 'categories.csv')}
        response = logged_in_client.post(
            '/import/categories',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert response.status_code == 200
        assert '导入完成' in response.data.decode('utf-8')

    def test_import_transactions_upload(self, logged_in_client, app):
        """上传交易预览"""
        # 先导入账户和分类
        data_acc = {'file': (io.BytesIO(ACCOUNTS_CSV.encode('utf-8')), 'accounts.csv')}
        logged_in_client.post(
            '/import/accounts',
            data=data_acc,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        data_cat = {'file': (io.BytesIO(CATEGORIES_CSV.encode('utf-8')), 'categories.csv')}
        logged_in_client.post(
            '/import/categories',
            data=data_cat,
            content_type='multipart/form-data',
            follow_redirects=True
        )

        data = {'file': (io.BytesIO(TRANSACTIONS_CSV.encode('utf-8')), 'transactions.csv')}
        response = logged_in_client.post(
            '/import/transactions/upload',
            data=data,
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_import_no_file(self, logged_in_client):
        """未选择文件"""
        response = logged_in_client.post(
            '/import/accounts',
            data={},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert response.status_code == 200
        assert '请选择文件' in response.data.decode('utf-8')

    def test_import_unauthenticated(self, client):
        """未登录访问导入页面"""
        response = client.get('/import', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')


# ===============================================================
# 需要额外导入
# ===============================================================

import io as io_module