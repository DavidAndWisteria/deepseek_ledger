import pytest
from app import db
from app.models import Family, User, Owner, UserRole


class TestFamilyRoutes:
    """家庭路由测试"""

    def test_family_page(self, logged_in_client):
        """家庭管理页面加载，验证成人计数正确"""
        response = logged_in_client.get('/family')
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '1 名成员' in content
        assert '1 名成人' in content

    def test_family_adult_count(self, logged_in_client, app, test_family):
        """验证家庭页面成人计数正确（区分成人/小孩）"""
        with app.app_context():
            child_user = User(username='child_test', role=UserRole.CHILD, family_id=test_family)
            child_user.set_password('password123')
            db.session.add(child_user)
            db.session.flush()
            child_owner = Owner(owner_name='小孩', family_id=test_family, user_id=child_user.id)
            db.session.add(child_owner)
            db.session.commit()
        
        response = logged_in_client.get('/family')
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        assert '2 名成员' in content
        assert '1 名成人' in content

    def test_add_member(self, logged_in_client, app, test_family):
        """添加小孩成员"""
        response = logged_in_client.post('/family/add-member', data={
            'owner_name': '新成员',
            'username': 'newmember',
            'password': 'password123',
            'role': 'CHILD'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            user = User.query.filter_by(username='newmember').first()
            assert user is not None
            assert user.role == UserRole.CHILD
            assert user.family_id == test_family
            assert user.owner is not None
            assert user.owner.owner_name == '新成员'

    def test_add_adult_member(self, logged_in_client, app, test_family):
        """添加成人成员"""
        response = logged_in_client.post('/family/add-member', data={
            'owner_name': '妈妈',
            'username': 'mother',
            'password': 'password123',
            'role': 'ADULT'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            user = User.query.filter_by(username='mother').first()
            assert user.is_adult() is True

    def test_edit_member(self, logged_in_client, app, test_user):
        """编辑成员信息"""
        with app.app_context():
            user = db.session.get(User, test_user)
            owner_id = user.owner.owner_id
        
        response = logged_in_client.post(f'/family/edit-member/{owner_id}', data={
            'owner_name': '改名后',
            'role': 'ADULT'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_member(self, logged_in_client, app, test_family):
        """删除成员"""
        with app.app_context():
            user = User(username='todelete', role=UserRole.CHILD, family_id=test_family)
            user.set_password('password123')
            db.session.add(user)
            db.session.flush()
            owner = Owner(owner_name='待删除', family_id=test_family, user_id=user.id)
            db.session.add(owner)
            db.session.commit()
            owner_id = owner.owner_id
        
        response = logged_in_client.post(f'/family/delete-member/{owner_id}', follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            deleted_owner = db.session.get(Owner, owner_id)
            assert deleted_owner is None

    def test_cannot_delete_self(self, logged_in_client, app, test_user):
        """不能删除自己"""
        with app.app_context():
            user = db.session.get(User, test_user)
            owner_id = user.owner.owner_id
        
        response = logged_in_client.post(f'/family/delete-member/{owner_id}', follow_redirects=True)
        assert response.status_code == 200

    def test_reset_password(self, logged_in_client, app, test_family):
        """重置成员密码"""
        with app.app_context():
            user = User(username='resetpwd', role=UserRole.CHILD, family_id=test_family)
            user.set_password('oldpassword')
            db.session.add(user)
            db.session.flush()
            owner = Owner(owner_name='密码重置', family_id=test_family, user_id=user.id)
            db.session.add(owner)
            db.session.commit()
            owner_id = owner.owner_id
        
        response = logged_in_client.post(f'/family/reset-password/{owner_id}', data={
            'new_password': 'newpassword123'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            user = User.query.filter_by(username='resetpwd').first()
            assert user.check_password('newpassword123') is True

    def test_family_unauthenticated(self, client):
        """未登录访问重定向"""
        response = client.get('/family', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')