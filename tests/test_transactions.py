from datetime import datetime, timezone
import pytest
from app import db
from app.models import Transaction, Account, Category, CategoryType, AccountType, TransactionStatus


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

    def test_update_status(self, logged_in_client, app, test_transaction):
        """测试更新单笔交易状态"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/VERIFIED',
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction.trans_status == TransactionStatus.VERIFIED

    def test_update_status_invalid(self, logged_in_client, test_transaction):
        """测试使用无效状态更新"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/INVALID',
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_batch_verify(self, logged_in_client, app, test_owner, test_account, test_category):
        """测试批量核对"""
        with app.app_context():
            t1 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-50.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            t2 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-30.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add_all([t1, t2])
            db.session.commit()
            ids = [t1.trans_id, t2.trans_id]
        
        response = logged_in_client.post(
            '/batch-verify',
            data={'trans_ids': ids},
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            for tid in ids:
                t = db.session.get(Transaction, tid)
                assert t.trans_status == TransactionStatus.VERIFIED

    def test_batch_verify_no_selection(self, logged_in_client):
        """测试空选择批量核对"""
        response = logged_in_client.post(
            '/batch-verify',
            data={},
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_dashboard_status_filter(self, logged_in_client, app, test_owner, test_account, test_category):
        """测试按状态筛选交易"""
        with app.app_context():
            t = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-80.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner,
                trans_status=TransactionStatus.VERIFIED
            )
            db.session.add(t)
            db.session.commit()
        
        response = logged_in_client.get('/?status=VERIFIED')
        assert response.status_code == 200
        
        response = logged_in_client.get('/?status=UNVERIFIED')
        assert response.status_code == 200

    def test_default_transaction_status(self, logged_in_client, app, test_owner, test_account, test_category):
        """测试手动添加的交易默认为未核对"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '200.00',
            'description': '新交易',
            'trans_date': '2026-01-15'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='新交易').first()
            assert transaction is not None
            assert transaction.trans_status == TransactionStatus.UNVERIFIED