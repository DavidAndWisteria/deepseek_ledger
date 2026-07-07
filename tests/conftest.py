import os
import shutil
import tempfile
import pytest
from app import create_app, db
from app.models import (
    User, Family, Owner, Account, Category, Transaction,
    AccountType, CategoryType, UserRole
)
from datetime import datetime, timezone


# 开发数据库路径
DEV_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'ledger.db')
BACKUP_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'ledger.db.backup')


def pytest_configure(config):
    """pytest 启动时备份开发数据库"""
    if os.path.exists(DEV_DB_PATH):
        shutil.copy2(DEV_DB_PATH, BACKUP_DB_PATH)


def pytest_unconfigure(config):
    """pytest 结束时恢复开发数据库"""
    if os.path.exists(BACKUP_DB_PATH):
        shutil.copy2(BACKUP_DB_PATH, DEV_DB_PATH)
        os.unlink(BACKUP_DB_PATH)


@pytest.fixture
def app():
    """创建测试Flask应用，使用临时数据库"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    app = create_app(test_config={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'SERVER_NAME': 'localhost',
    })
    
    with app.app_context():
        db.create_all()
    
    yield app
    
    with app.app_context():
        db.drop_all()
    
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_user(app):
    with app.app_context():
        family = Family(family_name='测试家庭')
        db.session.add(family)
        db.session.flush()
        
        user = User(username='testuser', role=UserRole.ADULT, family_id=family.family_id)
        user.set_password('password123')
        db.session.add(user)
        db.session.flush()
        
        owner = Owner(owner_name='测试用户', family_id=family.family_id, user_id=user.id)
        db.session.add(owner)
        db.session.commit()
        
        return user.id


@pytest.fixture
def logged_in_client(app, test_user):
    client = app.test_client()
    with app.app_context():
        user = db.session.get(User, test_user)
        assert user is not None
        client.post('/login', data={
            'username': user.username,
            'password': 'password123'
        }, follow_redirects=True)
    return client


@pytest.fixture
def test_owner(app, test_user):
    with app.app_context():
        user = db.session.get(User, test_user)
        assert user is not None
        assert user.owner is not None
        return user.owner.owner_id


@pytest.fixture
def test_family(app, test_user):
    with app.app_context():
        user = db.session.get(User, test_user)
        assert user is not None
        return user.family_id


@pytest.fixture
def test_account(app, test_owner):
    with app.app_context():
        account = Account(
            account_name='测试储蓄卡',
            account_type=AccountType.SAVING,
            account_custodian='测试银行',
            account_currency_name='HKD',
            account_owner_id=test_owner
        )
        db.session.add(account)
        db.session.commit()
        return account.account_id


@pytest.fixture
def test_category(app):
    with app.app_context():
        category = Category(
            category_name='餐饮',
            category_class='日常生活',
            category_subclass='饮食',
            category_type=CategoryType.EXPENSE
        )
        db.session.add(category)
        db.session.commit()
        return category.category_id


@pytest.fixture
def test_transaction(app, test_owner, test_account, test_category):
    with app.app_context():
        transaction = Transaction(
            trans_datetime=datetime.now(timezone.utc),
            trans_desc='测试午餐',
            trans_amount=-100.00,
            trans_account_id=test_account,
            trans_category_id=test_category,
            trans_owner_id=test_owner
        )
        db.session.add(transaction)
        db.session.commit()
        return transaction.trans_id
    
