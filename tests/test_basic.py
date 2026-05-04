"""基础功能冒烟测试"""


class TestBasicFunctionality:
    """基础冒烟测试 - 验证核心流程"""

    def test_app_exists(self, client):
        """测试应用可以启动"""
        assert client is not None

    def test_home_redirects_to_login(self, client):
        """测试首页重定向到登录"""
        response = client.get('/')
        assert response.status_code == 302  # 重定向

    def test_login_page_loads(self, client):
        """测试登录页面加载"""
        response = client.get('/login')
        assert response.status_code == 200

    def test_register_page_loads(self, client):
        """测试注册页面加载"""
        response = client.get('/register')
        assert response.status_code == 200

    def test_full_user_flow(self, client, app):
        """测试完整用户流程：注册 -> 登录 -> 添加记录 -> 查看"""
        # 1. 注册
        response = client.post('/register', data={
            'username': 'flowtest',
            'password': 'password123'
        }, follow_redirects=True)
        assert response.status_code == 200

        # 2. 如果注册后自动登录，直接添加记录
        # 否则先登录
        response = client.post('/add', data={
            'amount': '123.45',
            'category': '测试分类',
            'description': '流程测试',
            'record_type': 'expense'
        }, follow_redirects=True)
        
        # 如果被重定向到登录页，说明需要登录
        if '登录' in response.data.decode('utf-8'):
            # 登录
            client.post('/login', data={
                'username': 'flowtest',
                'password': 'password123'
            })
            # 重新添加记录
            response = client.post('/add', data={
                'amount': '123.45',
                'category': '测试分类',
                'description': '流程测试',
                'record_type': 'expense'
            }, follow_redirects=True)

        # 3. 查看仪表盘
        response = client.get('/')
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '测试分类' in content
        assert '123.45' in content