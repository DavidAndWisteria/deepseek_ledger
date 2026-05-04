import pytest
from app import db
from app.models import User, Family, Owner, UserRole


class TestAuthRoutes:
    """认证路由测试"""

    def test_login_page(self, client):
        response = client.get('/login')
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')

    def test_register_page(self, client):
        response = client.get('/register')
        assert response.status_code == 200
        assert '注册' in response.data.decode('utf-8')

    def test_register_success(self, client, app):
        response = client.post('/register', data={
            'username': 'newuser',
            'password': 'password123',
            'family_name': '新家庭',
            'owner_name': '新成员',
            'role': 'ADULT'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            assert user is not None
            assert user.family is not None
            assert user.owner is not None

    def test_register_empty_username(self, client):
        response = client.post('/register', data={
            'username': '',
            'password': 'password123',
            'family_name': '家庭',
            'owner_name': '成员'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_register_short_password(self, client):
        response = client.post('/register', data={
            'username': 'testuser2',
            'password': '1234567',
            'family_name': '家庭',
            'owner_name': '成员'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_register_duplicate_username(self, client, test_user):
        response = client.post('/register', data={
            'username': 'testuser',
            'password': 'password123',
            'family_name': '家庭',
            'owner_name': '成员'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_success(self, client, test_user):
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_wrong_password(self, client, test_user):
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_logout(self, logged_in_client):
        response = logged_in_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')

    def test_protected_route_redirect(self, client):
        response = client.get('/', follow_redirects=True)
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')