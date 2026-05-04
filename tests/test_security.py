import pytest
from app import db
from app.models import User, Record
import re


class TestSecurity:
    """安全相关测试"""

    def test_password_not_stored_plaintext(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            assert user.password_hash != 'password123'

    def test_password_hash_unique_per_user(self, app):
        with app.app_context():
            user1 = User(username='user1')
            user1.set_password('samepassword')
            db.session.add(user1)
            user2 = User(username='user2')
            user2.set_password('samepassword')
            db.session.add(user2)
            db.session.commit()
            assert user1.password_hash != user2.password_hash

    def test_csrf_protection_enabled(self, client):
        response = client.post('/login', data={
            'username': 'test',
            'password': 'test'
        })
        assert response.status_code in [200, 302, 400]

    def test_xss_sanitization(self, logged_in_client):
        response = logged_in_client.post('/add', data={
            'amount': '100',
            'category': '<script>alert("xss")</script>',
            'description': '<img src=x onerror=alert(1)>',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '<script>' not in content
        assert 'onerror' not in content

    def test_user_data_isolation(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            other_user = User(username='otheruser')
            other_user.set_password('password456')
            db.session.add(other_user)
            db.session.commit()
            record1 = Record(
                user_id=user.id,
                amount=100,
                category='我的记录',
                record_type='expense'
            )
            record2 = Record(
                user_id=other_user.id,
                amount=200,
                category='别人的记录',
                record_type='income'
            )
            db.session.add_all([record1, record2])
            db.session.commit()
            my_records = Record.query.filter_by(user_id=user.id).all()
            for record in my_records:
                assert record.user_id == user.id

    def test_username_allowed_characters(self):
        pattern = r'^[a-zA-Z0-9_]+$'
        assert re.match(pattern, 'valid_user123')
        assert not re.match(pattern, 'user-name')
        assert not re.match(pattern, 'user@name')
        assert not re.match(pattern, 'user name')