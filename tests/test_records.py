import pytest
from app import db
from app.models import Record, User


class TestRecordRoutes:
    """记录路由测试"""

    def test_dashboard_authenticated(self, logged_in_client):
        response = logged_in_client.get('/')
        assert response.status_code == 200

    def test_dashboard_unauthenticated(self, client):
        response = client.get('/', follow_redirects=True)
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')

    def test_add_expense_record(self, logged_in_client, app, test_user):
        response = logged_in_client.post('/add', data={
            'amount': '150.00',
            'category': '餐饮',
            'description': '晚餐',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record.query.filter_by(user_id=user.id, amount=150.00).first()
            assert record is not None
            assert record.category == '餐饮'
            assert record.record_type == 'expense'

    def test_add_income_record(self, logged_in_client, app, test_user):
        response = logged_in_client.post('/add', data={
            'amount': '5000.00',
            'category': '工资',
            'description': '月薪',
            'record_type': 'income'
        }, follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            user = db.session.get(User, test_user)
            record = Record.query.filter_by(user_id=user.id, amount=5000.00).first()
            assert record is not None
            assert record.record_type == 'income'

    def test_add_record_zero_amount(self, logged_in_client):
        response = logged_in_client.post('/add', data={
            'amount': '0',
            'category': '测试',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_record_negative_amount(self, logged_in_client):
        response = logged_in_client.post('/add', data={
            'amount': '-100',
            'category': '测试',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_record_invalid_amount(self, logged_in_client):
        response = logged_in_client.post('/add', data={
            'amount': 'abc',
            'category': '测试',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_record_empty_category(self, logged_in_client):
        response = logged_in_client.post('/add', data={
            'amount': '100',
            'category': '',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_own_record(self, logged_in_client, app, sample_records):
        record_id = sample_records[0]
        response = logged_in_client.post(f'/delete/{record_id}', follow_redirects=True)
        assert response.status_code == 200
        with app.app_context():
            record = db.session.get(Record, record_id)
            assert record is None

    def test_delete_nonexistent_record(self, logged_in_client):
        response = logged_in_client.post('/delete/99999', follow_redirects=True)
        assert response.status_code == 404

    def test_dashboard_shows_records(self, logged_in_client, app, sample_records):
        response = logged_in_client.get('/')
        content = response.data.decode('utf-8')
        assert response.status_code == 200
        with app.app_context():
            record = db.session.get(Record, sample_records[0])
            assert record.category in content

    def test_dashboard_calculates_totals(self, logged_in_client, sample_records):
        response = logged_in_client.get('/')
        content = response.data.decode('utf-8')
        assert response.status_code == 200
        assert '5000.00' in content
        assert '350.00' in content
        assert '4650.00' in content

    def test_add_record_unauthenticated(self, client):
        response = client.post('/add', data={
            'amount': '100',
            'category': '测试',
            'record_type': 'expense'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')

    def test_delete_record_unauthenticated(self, client):
        response = client.post('/delete/1', follow_redirects=True)
        assert response.status_code == 200
        assert '登录' in response.data.decode('utf-8')