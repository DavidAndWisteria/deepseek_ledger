import pytest
from app import db
from app.models import Transaction, Account, Category, CategoryType, AccountType


class TestTransactionRoutes:
    """交易路由测试"""

    def test_dashboard(self, logged_in_client):
        response = logged_in_client.get('/')
        assert response.status_code == 200

    def test_add_income(self, logged_in_client, app, test_owner, test_account, test_category):
        response = logged_in_client.post('/add', data={
            'trans_type': 'income',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '5000.00',
            'description': '工资',
            'trans_date': '2026-01-15'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='工资').first()
            assert transaction is not None
            assert transaction.trans_amount == 5000.00
            assert transaction.is_income() is True

    def test_add_expense(self, logged_in_client, app, test_owner, test_account, test_category):
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '150.00',
            'description': '午餐',
            'trans_date': '2026-01-15'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='午餐').first()
            assert transaction is not None
            assert transaction.trans_amount == -150.00

    def test_add_transfer(self, logged_in_client, app, test_owner, test_account, test_category):
        # 创建第二个账户
        with app.app_context():
            account2 = Account(
                account_name='信用卡',
                account_type=AccountType.CREDIT_CARD,
                account_custodian='银行',
                account_owner_id=test_owner
            )
            db.session.add(account2)
            db.session.commit()
            to_account_id = account2.account_id
        
        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': test_account,
            'to_account_id': to_account_id,
            'category_id': test_category,
            'amount': '1000.00',
            'description': '还款',
            'trans_date': '2026-01-15'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transactions = Transaction.query.filter(
                Transaction.trans_desc.contains('还款')
            ).all()
            assert len(transactions) == 2

    def test_delete_transaction(self, logged_in_client, app, test_transaction):
        response = logged_in_client.post(f'/delete/{test_transaction}', follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction is None

    def test_dashboard_unauthenticated(self, client):
        response = client.get('/', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')