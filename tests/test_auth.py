import pytest
from app import db
from app.models import User
from flask import url_for


class TestAuthRoutes:
    """认证路由测试"""

    def test_login_page_get(self, client):
        """测试访问登录页面"""
        response = client.get('/login')
        assert response.status_code == 200

    def test_register_page_get(self, client):
        """测试访问注册页面"""
        response = client.get('/register')
        assert response.status_code == 200

    def test_register_success(self, client, app):
        """测试成功注册"""
        response = client.post('/register', data={
            'username': 'newuser',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        # 注册成功后应跳转到仪表盘
        assert '仪表盘' in response.data.decode('utf-8') or '账本' in response.data.decode('utf-8')

        # 验证用户已在数据库中
        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            assert user is not None
            assert user.check_password('password123')

    def test_register_empty_username(self, client):
        """测试注册空用户名"""
        response = client.post('/register', data={
            'username': '',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '用户名' in response.data.decode('utf-8')

    def test_register_empty_password(self, client):
        """测试注册空密码"""
        response = client.post('/register', data={
            'username': 'testuser2',
            'password': ''
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '密码' in response.data.decode('utf-8')

    def test_register_short_username(self, client):
        """测试注册过短的用户名"""
        response = client.post('/register', data={
            'username': 'ab',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '用户名' in response.data.decode('utf-8')

    def test_register_short_password(self, client):
        """测试注册过短的密码"""
        response = client.post('/register', data={
            'username': 'validuser',
            'password': '1234567'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '密码' in response.data.decode('utf-8')

    def test_register_duplicate_username(self, client, test_user):
        """测试注册重复用户名"""
        response = client.post('/register', data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '已存在' in response.data.decode('utf-8') or '已被注册' in response.data.decode('utf-8')

    def test_register_invalid_username_chars(self, client):
        """测试注册包含特殊字符的用户名"""
        response = client.post('/register', data={
            'username': 'user@name!',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '用户名' in content

    def test_login_success(self, client, test_user):
        """测试成功登录"""
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '仪表盘' in response.data.decode('utf-8') or '账本' in response.data.decode('utf-8')

    def test_login_wrong_password(self, client, test_user):
        """测试错误密码登录"""
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '错误' in response.data.decode('utf-8')

    def test_login_wrong_username(self, client):
        """测试不存在的用户名登录"""
        response = client.post('/login', data={
            'username': 'nonexistent',
            'password': 'password123'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '错误' in response.data.decode('utf-8')

    def test_logout(self, logged_in_client):
        """测试退出登录"""
        response = logged_in_client.get('/logout', follow_redirects=True)

        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')

    def test_protected_route_redirect(self, client):
        """测试未登录访问受保护页面"""
        response = client.get('/', follow_redirects=True)

        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')