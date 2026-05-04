import pytest
from app import db
from app.models import User, Record
from datetime import datetime, timezone


class TestUserModel:
    """用户模型测试"""

    def test_create_user(self, app):
        with app.app_context():
            user = User(username='newuser')
            user.set_password('mypassword')
            db.session.add(user)
            db.session.commit()
            assert user.id is not None
            assert user.username == 'newuser'
            assert user.password_hash != 'mypassword'
            assert user.created_at is not None

    def test_password_hashing(self, app):
        with app.app_context():
            user = User(username='testhash')
            user.set_password('correct_password')
            assert user.password_hash != 'correct_password'
            assert len(user.password_hash) > 20

    def test_password_verification_correct(self, app):
        with app.app_context():
            user = User(username='testverify')
            user.set_password('correct_password')
            assert user.check_password('correct_password') is True

    def test_password_verification_wrong(self, app):
        with app.app_context():
            user = User(username='testwrong')
            user.set_password('correct_password')
            assert user.check_password('wrong_password') is False

    def test_password_verification_empty(self, app):
        with app.app_context():
            user = User(username='testempty')
            user.set_password('somepassword')
            assert user.check_password('') is False

    def test_unique_username(self, app):
        with app.app_context():
            user1 = User(username='duplicate')
            user1.set_password('password1')
            db.session.add(user1)
            db.session.commit()
            user2 = User(username='duplicate')
            user2.set_password('password2')
            db.session.add(user2)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()


class TestRecordModel:
    """记录模型测试"""

    def test_create_expense_record(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record(
                user_id=user.id,
                amount=100.50,
                category='餐饮',
                description='午餐',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            assert record.id is not None
            assert record.amount == 100.50
            assert record.category == '餐饮'
            assert record.description == '午餐'
            assert record.record_type == 'expense'
            assert record.date is not None

    def test_create_income_record(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record(
                user_id=user.id,
                amount=5000.00,
                category='工资',
                description='月薪',
                record_type='income'
            )
            db.session.add(record)
            db.session.commit()
            assert record.record_type == 'income'
            assert record.amount == 5000.00

    def test_record_user_relationship(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record(
                user_id=user.id,
                amount=50.00,
                category='交通',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            assert record.user_id == user.id
            assert record.user.username == 'testuser'

    def test_record_without_description(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record(
                user_id=user.id,
                amount=30.00,
                category='其他',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            assert record.description is None

    def test_record_amount_decimal(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record(
                user_id=user.id,
                amount=99.99,
                category='测试',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            assert record.amount == 99.99

    def test_record_date_auto_set(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            before = datetime.now(timezone.utc)
            record = Record(
                user_id=user.id,
                amount=10.00,
                category='测试',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            after = datetime.now(timezone.utc)
            assert record.date.replace(tzinfo=timezone.utc) >= before
            assert record.date.replace(tzinfo=timezone.utc) <= after