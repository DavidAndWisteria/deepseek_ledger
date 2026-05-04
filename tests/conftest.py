import os
import tempfile
import pytest
from app import create_app, db
from app.models import User, Record


@pytest.fixture
def app():
    """创建测试用的Flask应用"""
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app()
    app.config.update({
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
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """创建测试命令行运行器"""
    return app.test_cli_runner()


@pytest.fixture
def test_user(app):
    """创建测试用户，返回用户ID避免 DetachedInstanceError"""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        # 返回 user_id 而不是 user 对象
        return user.id


@pytest.fixture
def logged_in_client(client, app, test_user):
    """创建已登录的测试客户端"""
    with app.app_context():
        user = db.session.get(User, test_user)
        client.post('/login', data={
            'username': user.username,
            'password': 'password123'
        }, follow_redirects=True)
    return client


@pytest.fixture
def sample_records(app, test_user):
    """创建示例记录，返回记录ID列表"""
    with app.app_context():
        records = [
            Record(
                user_id=test_user,
                amount=100.00,
                category='餐饮',
                description='午餐',
                record_type='expense'
            ),
            Record(
                user_id=test_user,
                amount=50.00,
                category='交通',
                description='地铁',
                record_type='expense'
            ),
            Record(
                user_id=test_user,
                amount=5000.00,
                category='工资',
                description='月薪',
                record_type='income'
            ),
            Record(
                user_id=test_user,
                amount=200.00,
                category='购物',
                description='日用品',
                record_type='expense'
            ),
        ]
        for record in records:
            db.session.add(record)
        db.session.commit()
        # 返回记录ID列表
        return [r.id for r in records]