import io
import pytest
from app import db
from app.models import (
    Account, Owner, User,
    AccountType,
    BluecoinsAccountMapping
)
from app.services.import_service import ImportService
from sqlalchemy import select, func


# ===============================================================
# 测试用 CSV
# ===============================================================

ACCOUNTS_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Dav - ZA",62,"众安港币活期",,"SAVING",2022-01-24,,"众安银行","HKD","测试用户"
"Dav Master",1,"Dav Master",,"CREDIT_CARD",2021-01-01,,"中信银行","HKD","测试用户"
"Dav - 八达通",2,"八达通",,"CASH",2021-01-01,,"八达通","HKD","测试用户"
"""

EMPTY_ACCOUNT_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"EmptyAcc",99,,,,,,,,
"""

DUPLICATE_ID_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Acc1",100,"账户1",,"SAVING",2022-01-01,,"银行1","HKD","测试用户"
"Acc2",100,"账户2",,"SAVING",2022-01-01,,"银行2","HKD","测试用户"
"""

DUPLICATE_COMBO_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"Acc1",200,"相同账户",,"SAVING",2022-01-01,,"相同银行","HKD","测试用户"
"Acc2",201,"相同账户",,"SAVING",2022-01-01,,"相同银行","HKD","测试用户"
"""

FAMILY_OWNER_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"FamilyAcc",300,"家庭账户",,"SAVING",2023-06-15,,"家庭银行","HKD","测试家庭"
"""

CLOSE_DATE_NONE_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"OpenAcc",400,"未关闭账户",,"SAVING",2024-03-01,,"某银行","HKD","测试用户"
"""

CLOSE_DATE_SET_CSV = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"ClosedAcc",500,"已关闭账户",,"SAVING",2020-01-01,2023-12-31,"某银行","HKD","测试用户"
"""


# ===============================================================
# 辅助函数
# ===============================================================

def count_accounts():
    """返回 Account 表行数 (SQLAlchemy 2.0)"""
    stmt = select(func.count()).select_from(Account)
    return db.session.scalar(stmt)


def count_mappings():
    """返回 BluecoinsAccountMapping 表行数 (SQLAlchemy 2.0)"""
    stmt = select(func.count()).select_from(BluecoinsAccountMapping)
    return db.session.scalar(stmt)


# ===============================================================
# 测试类
# ===============================================================

class TestImportAccounts:
    """账户导入测试"""

    def test_import_basic(self, app, test_user):
        """基本导入：3 个账户全部成功"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(ACCOUNTS_CSV)

            assert result['success'] == 3
            assert result['skipped'] == 0
            assert result['failed'] == 0

            # 验证账户已创建
            assert db.session.scalars(
                select(Account).where(Account.account_name == '众安港币活期')
            ).first() is not None
            assert db.session.scalars(
                select(Account).where(Account.account_name == 'Dav Master')
            ).first() is not None
            assert db.session.scalars(
                select(Account).where(Account.account_name == '八达通')
            ).first() is not None

    def test_import_creates_accounts(self, app, test_user):
        """导入后账户属性正确"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '众安港币活期')
            ).first()
            assert acc is not None
            assert acc.account_type == AccountType.SAVING
            assert acc.account_custodian == '众安银行'
            assert acc.account_currency_name == 'HKD'

    def test_import_creates_mappings(self, app, test_user):
        """导入后创建 Bluecoins 映射"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)

            mapping = db.session.scalars(
                select(BluecoinsAccountMapping).where(
                    BluecoinsAccountMapping.bluecoins_name == 'Dav - ZA'
                )
            ).first()
            assert mapping is not None
            assert mapping.is_manual is False

            acc = db.session.get(Account, mapping.account_id)
            assert acc is not None
            assert acc.account_name == '众安港币活期'

    def test_import_skip_existing(self, app, test_user):
        """重复导入全部跳过"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            # 第一次
            result1 = service.import_accounts_csv(ACCOUNTS_CSV)
            assert result1['success'] == 3
            # 第二次：新建 service 实例（模拟重新导入）
            service2 = ImportService(user)
            result2 = service2.import_accounts_csv(ACCOUNTS_CSV)
            assert result2['skipped'] == 3
            assert result2['success'] == 0

    def test_import_skip_empty_row(self, app, test_user):
        """跳过所有字段为空的行"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(EMPTY_ACCOUNT_CSV)

            assert result['skipped'] == 1
            assert result['success'] == 0

    def test_import_skip_duplicate_id(self, app, test_user):
        """id 重复的跳过第二个"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(DUPLICATE_ID_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1

    def test_import_skip_duplicate_combination(self, app, test_user):
        """完全重复组合跳过第二个"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(DUPLICATE_COMBO_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1

    def test_import_close_date_none(self, app, test_user):
        """close_date 为空时保持 None（使用中）"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(CLOSE_DATE_NONE_CSV)

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '未关闭账户')
            ).first()
            assert acc is not None
            assert acc.account_close_date is None

    def test_import_close_date_set(self, app, test_user):
        """close_date 有值时正确解析"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(CLOSE_DATE_SET_CSV)

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '已关闭账户')
            ).first()
            assert acc is not None
            assert acc.account_close_date is not None
            assert acc.account_close_date.year == 2023
            assert acc.account_close_date.month == 12
            assert acc.account_close_date.day == 31

    def test_import_create_date_correct(self, app, test_user):
        """create_date 使用 CSV 中的日期而非当前日期"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '众安港币活期')
            ).first()
            assert acc is not None
            assert acc.account_create_date is not None
            assert acc.account_create_date.year == 2022
            assert acc.account_create_date.month == 1
            assert acc.account_create_date.day == 24

    def test_import_family_owner(self, app, test_user):
        """owner 为家庭名时创建家庭共享 Owner"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(FAMILY_OWNER_CSV)

            assert result['success'] == 1

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '家庭账户')
            ).first()
            assert acc is not None
            # 拥有者应为家庭共享 Owner
            owner = db.session.get(Owner, acc.account_owner_id)
            assert owner is not None
            assert owner.owner_name == '测试家庭'

    def test_import_family_owner_no_user(self, app, test_user):
        """家庭共享 Owner 的 user_id 为 None"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(FAMILY_OWNER_CSV)

            acc = db.session.scalars(
                select(Account).where(Account.account_name == '家庭账户')
            ).first()
            assert acc is not None
            owner = db.session.get(Owner, acc.account_owner_id)
            assert owner is not None
            assert owner.user_id is None

    def test_import_unmatched_owner_fails(self, app, test_user):
        """无法匹配 owner 时标记为失败"""
        csv_data = """账户,id,account_name,account_other_name,account_type,account_create_date,account_close_date,account_custodian,account_currency_name,account_owner
"BadAcc",600,"坏账户",,"SAVING",2022-01-01,,"某银行","HKD","不存在的用户"
"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(csv_data)

            assert result['failed'] == 1
            assert result['success'] == 0

    def test_import_result_details(self, app, test_user):
        """导入结果包含详细信息"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv(ACCOUNTS_CSV)

            assert len(result['details']) == 3
            for detail in result['details']:
                assert detail['status'] == 'success'
                assert 'name' in detail
                assert 'account_name' in detail

    def test_import_empty_csv(self, app, test_user):
        """空 CSV 不报错"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv('')

            assert result['success'] == 0
            assert result['failed'] == 0
            assert result['skipped'] == 0

    def test_import_malformed_csv(self, app, test_user):
        """格式错误的 CSV 不报错"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_accounts_csv('not,a,csv\n1,2,3')

            assert result['success'] == 0

    def test_bluecoins_mapping_no_owner_id(self, app, test_user):
        """bluecoins_account_mapping 不存储 owner_id"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_accounts_csv(ACCOUNTS_CSV)

            mapping = db.session.scalars(
                select(BluecoinsAccountMapping).where(
                    BluecoinsAccountMapping.bluecoins_name == 'Dav - ZA'
                )
            ).first()
            assert mapping is not None
            # 验证没有 owner_id 属性
            assert not hasattr(mapping, 'owner_id')
