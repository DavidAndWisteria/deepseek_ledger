import pytest
from app import db
from app.models import (
    User, Family, Owner, Account, Category, Transaction,
    AccountType, CategoryType, UserRole, TransactionStatus
)
from datetime import datetime, timezone
from sqlalchemy import select


class TestUserModel:
    """用户模型测试"""

    def test_create_user(self, app, test_family):
        with app.app_context():
            user = User(username='newuser', role=UserRole.ADULT, family_id=test_family)
            user.set_password('mypassword')
            db.session.add(user)
            db.session.commit()
            assert user.id is not None
            assert user.username == 'newuser'
            assert user.password_hash != 'mypassword'
            assert user.role == UserRole.ADULT
            assert user.is_adult() is True

    def test_child_user(self, app, test_family):
        with app.app_context():
            user = User(username='child', role=UserRole.CHILD, family_id=test_family)
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            assert user.is_adult() is False
            assert user.can_view_family_data() is False

    def test_password_verification(self, app, test_family):
        with app.app_context():
            user = User(username='testpwd', role=UserRole.ADULT, family_id=test_family)
            user.set_password('correct')
            assert user.check_password('correct') is True
            assert user.check_password('wrong') is False

    def test_unique_username(self, app, test_family):
        with app.app_context():
            user1 = User(username='unique_test', role=UserRole.ADULT, family_id=test_family)
            user1.set_password('pwd')
            db.session.add(user1)
            db.session.commit()
            
            user2 = User(username='unique_test', role=UserRole.CHILD, family_id=test_family)
            user2.set_password('pwd')
            db.session.add(user2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()


class TestFamilyModel:
    """家庭模型测试"""

    def test_create_family(self, app):
        with app.app_context():
            family = Family(family_name='新家庭')
            db.session.add(family)
            db.session.commit()
            assert family.family_id is not None
            assert family.family_name == '新家庭'
            assert family.created_at is not None

    def test_family_members_relationship(self, app):
        with app.app_context():
            family = Family(family_name='关系测试')
            db.session.add(family)
            db.session.flush()
            
            user = User(username='member1', role=UserRole.ADULT, family_id=family.family_id)
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()
            assert user.family is not None
            assert user.family.family_name == '关系测试'


class TestOwnerModel:
    """所有者模型测试"""

    def test_create_owner(self, app, test_family, test_user):
        with app.app_context():
            owner = Owner(owner_name='新成员', family_id=test_family, user_id=test_user)
            db.session.add(owner)
            db.session.commit()
            assert owner.owner_id is not None
            assert owner.owner_name == '新成员'
            assert owner.user is not None
            assert owner.user.username == 'testuser'


class TestAccountModel:
    """账户模型测试"""

    def test_create_account(self, app, test_owner):
        with app.app_context():
            account = Account(
                account_name='现金钱包',
                account_type=AccountType.CASH,
                account_custodian='支付宝',
                account_currency_name='CNY',
                account_owner_id=test_owner
            )
            db.session.add(account)
            db.session.commit()
            assert account.account_id is not None
            assert account.account_name == '现金钱包'
            assert account.account_type == AccountType.CASH
            assert account.account_currency_name == 'CNY'

    def test_account_close_date(self, app, test_owner):
        with app.app_context():
            from datetime import date
            account = Account(
                account_name='已关闭账户',
                account_type=AccountType.SAVING,
                account_custodian='某银行',
                account_owner_id=test_owner,
                account_close_date=date(2025, 12, 31)
            )
            db.session.add(account)
            db.session.commit()
            assert account.account_close_date == date(2025, 12, 31)


class TestCategoryModel:
    """分类模型测试"""

    def test_create_category(self, app):
        with app.app_context():
            category = Category(
                category_name='工资',
                category_class='职业收入',
                category_subclass='主业',
                category_type=CategoryType.INCOME
            )
            db.session.add(category)
            db.session.commit()
            assert category.category_id is not None
            assert category.category_type == CategoryType.INCOME
            assert category.category_type.value == 'I'

    def test_category_with_alias(self, app):
        with app.app_context():
            category = Category(
                category_name='餐饮',
                category_other_name='吃饭',
                category_class='日常生活',
                category_subclass='饮食',
                category_type=CategoryType.EXPENSE
            )
            db.session.add(category)
            db.session.commit()
            assert category.category_other_name == '吃饭'

    def test_category_types(self, app):
        with app.app_context():
            types = [
                ('收入类', CategoryType.INCOME, 'I'),
                ('支出类', CategoryType.EXPENSE, 'E'),
                ('转账类', CategoryType.TRANSFER, 'T'),
                ('特殊类', CategoryType.SPECIAL, 'S'),
            ]
            for name, enum_type, expected_value in types:
                category = Category(
                    category_name=name,
                    category_class='测试',
                    category_subclass='',
                    category_type=enum_type
                )
                assert category.category_type.value == expected_value


class TestTransactionModel:
    """交易模型测试"""

    def test_create_income(self, app, test_owner, test_account, test_category):
        with app.app_context():
            transaction = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='工资',
                trans_amount=5000.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(transaction)
            db.session.commit()
            assert transaction.trans_id is not None
            assert transaction.is_income() is True
            assert transaction.is_expense() is False
            assert transaction.is_transfer() is False

    def test_create_expense(self, app, test_owner, test_account, test_category):
        with app.app_context():
            transaction = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='午餐',
                trans_amount=-100.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(transaction)
            db.session.commit()
            assert transaction.is_expense() is True
            assert transaction.is_income() is False

    def test_create_transfer(self, app, test_owner, test_account, test_category):
        with app.app_context():
            # 创建第二个账户
            account2 = Account(
                account_name='信用卡',
                account_type=AccountType.CREDIT_CARD,
                account_custodian='某银行',
                account_owner_id=test_owner
            )
            db.session.add(account2)
            db.session.flush()
            
            # 转出
            trans_out = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='还款转出',
                trans_amount=-1000.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(trans_out)
            db.session.flush()
            
            # 转入
            trans_in = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='还款转入',
                trans_amount=1000.00,
                trans_account_id=account2.account_id,
                trans_category_id=test_category,
                trans_owner_id=test_owner,
                trans_counter_id=trans_out.trans_id
            )
            db.session.add(trans_in)
            db.session.flush()
            
            trans_out.trans_counter_id = trans_in.trans_id
            db.session.commit()
            
            assert trans_out.is_transfer() is True
            assert trans_in.is_transfer() is True
            assert trans_out.counter_transaction is not None
            assert trans_out.counter_transaction.trans_id == trans_in.trans_id
            assert trans_in.counter_transaction is not None
            assert trans_in.counter_transaction.trans_id == trans_out.trans_id

    def test_transaction_currency(self, app, test_owner, test_account, test_category):
        with app.app_context():
            transaction = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=100.00,
                trans_currency_name='USD',
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(transaction)
            db.session.commit()
            assert transaction.trans_currency_name == 'USD'

    def test_transaction_default_status(self, app, test_owner, test_account, test_category):
        """测试交易默认状态为未核对"""
        with app.app_context():
            transaction = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=50.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(transaction)
            db.session.commit()
            assert transaction.trans_status == TransactionStatus.UNVERIFIED

    def test_transaction_status_change(self, app, test_transaction):
        """测试修改交易状态"""
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction is not None
            assert transaction.trans_status == TransactionStatus.UNVERIFIED
            transaction.trans_status = TransactionStatus.VERIFIED
            db.session.commit()
            assert transaction.trans_status == TransactionStatus.VERIFIED

    def test_transaction_status_enum_values(self, app, test_transaction):
        """测试所有状态枚举值"""
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            for status in TransactionStatus:
                assert transaction is not None
                transaction.trans_status = status
                db.session.commit()
                assert transaction.trans_status == status
