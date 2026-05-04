import pytest
from app import db
from app.models import Category, CategoryType


class TestCategoryRoutes:
    """分类路由测试"""

    def test_categories_page(self, logged_in_client):
        response = logged_in_client.get('/categories')
        assert response.status_code == 200

    def test_add_category(self, logged_in_client, app):
        response = logged_in_client.post('/categories/add', data={
            'category_name': '交通',
            'category_class': '日常生活',
            'category_subclass': '出行',
            'category_type': 'E'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            category = Category.query.filter_by(category_name='交通').first()
            assert category is not None
            assert category.category_type == CategoryType.EXPENSE

    def test_add_category_with_alias(self, logged_in_client, app):
        response = logged_in_client.post('/categories/add', data={
            'category_name': '餐饮',
            'category_other_name': '吃饭',
            'category_class': '日常生活',
            'category_subclass': '饮食',
            'category_type': 'E'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            category = Category.query.filter_by(category_name='餐饮').first()
            assert category.category_other_name == '吃饭'

    def test_add_income_category(self, logged_in_client, app):
        response = logged_in_client.post('/categories/add', data={
            'category_name': '工资',
            'category_class': '职业收入',
            'category_subclass': '主业',
            'category_type': 'I'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            category = Category.query.filter_by(category_name='工资').first()
            assert category.category_type == CategoryType.INCOME

    def test_edit_category(self, logged_in_client, app, test_category):
        response = logged_in_client.post(f'/categories/{test_category}/edit', data={
            'category_name': '美食',
            'category_class': '日常生活',
            'category_subclass': '饮食',
            'category_type': 'E'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            category = db.session.get(Category, test_category)
            assert category.category_name == '美食'

    def test_delete_category(self, logged_in_client, app, test_category):
        response = logged_in_client.post(f'/categories/{test_category}/delete', follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            category = db.session.get(Category, test_category)
            assert category is None

    def test_categories_unauthenticated(self, client):
        response = client.get('/categories', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')