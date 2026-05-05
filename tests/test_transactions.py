from datetime import datetime, timezone
import pytest
from app import db
from app.models import Transaction, Account, Category, CategoryType, AccountType, TransactionStatus


class TestTransactionRoutes:
    """交易路由测试"""

    def test_dashboard(self, logged_in_client):
        """仪表盘页面加载"""
        response = logged_in_client.get('/')
        assert response.status_code == 200

    def test_add_income(self, logged_in_client, app, test_owner, test_account, test_category):
        """添加收入交易"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'income',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '5000.00',
            'description': '工资',
            'trans_date': '2026-01-15',
            'trans_time': '09:00'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='工资').first()
            assert transaction is not None
            assert transaction.trans_amount == 5000.00
            assert transaction.is_income() is True
            assert transaction.trans_status == TransactionStatus.UNVERIFIED

    def test_add_expense(self, logged_in_client, app, test_owner, test_account, test_category):
        """添加支出交易"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '150.00',
            'description': '午餐',
            'trans_date': '2026-01-15',
            'trans_time': '12:30'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='午餐').first()
            assert transaction is not None
            assert transaction.trans_amount == -150.00
            assert transaction.is_expense() is True

    def test_add_transfer(self, logged_in_client, app, test_owner, test_account, test_category):
        """添加转账交易（生成两条配对记录）"""
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
            'trans_date': '2026-01-15',
            'trans_time': '10:00'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transactions = Transaction.query.filter(
                Transaction.trans_desc.contains('还款')
            ).all()
            assert len(transactions) == 2

    def test_delete_transaction(self, logged_in_client, app, test_transaction):
        """删除交易"""
        response = logged_in_client.post(f'/delete/{test_transaction}', follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction is None

    def test_dashboard_unauthenticated(self, client):
        """未登录访问重定向"""
        response = client.get('/', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')

    def test_update_status(self, logged_in_client, app, test_transaction):
        """更新单笔交易状态为已核对"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/VERIFIED',
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction.trans_status == TransactionStatus.VERIFIED

    def test_update_status_to_unverified(self, logged_in_client, app, test_transaction):
        """更新交易状态回未核对"""
        with app.app_context():
            t = db.session.get(Transaction, test_transaction)
            t.trans_status = TransactionStatus.VERIFIED
            db.session.commit()
        
        response = logged_in_client.post(
            f'/status/{test_transaction}/UNVERIFIED',
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction.trans_status == TransactionStatus.UNVERIFIED

    def test_update_status_to_flagged(self, logged_in_client, app, test_transaction):
        """标记交易为有疑问"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/FLAGGED',
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction.trans_status == TransactionStatus.FLAGGED

    def test_update_status_invalid(self, logged_in_client, test_transaction):
        """使用无效状态更新"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/INVALID',
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_batch_verify(self, logged_in_client, app, test_owner, test_account, test_category):
        """批量核对"""
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
        """空选择批量核对"""
        response = logged_in_client.post(
            '/batch-verify',
            data={},
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_dashboard_status_filter(self, logged_in_client, app, test_owner, test_account, test_category):
        """按状态筛选交易"""
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
        
        response = logged_in_client.get('/?status=VERIFIED&tab=list-tab')
        assert response.status_code == 200
        
        response = logged_in_client.get('/?status=UNVERIFIED&tab=list-tab')
        assert response.status_code == 200

    def test_dashboard_category_filter(self, logged_in_client, app, test_owner, test_account, test_category):
        """按分类筛选交易"""
        with app.app_context():
            new_cat = Category(
                category_name='交通',
                category_class='日常生活',
                category_subclass='出行',
                category_type=CategoryType.EXPENSE
            )
            db.session.add(new_cat)
            db.session.flush()
            
            t = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-20.00,
                trans_account_id=test_account,
                trans_category_id=new_cat.category_id,
                trans_owner_id=test_owner
            )
            db.session.add(t)
            db.session.commit()
        
        response = logged_in_client.get(f'/?category_id={test_category}&tab=list-tab')
        assert response.status_code == 200

    def test_dashboard_account_filter(self, logged_in_client, app, test_owner, test_account, test_category):
        """按账户筛选交易"""
        with app.app_context():
            account2 = Account(
                account_name='另一个账户',
                account_type=AccountType.SAVING,
                account_custodian='测试银行',
                account_currency_name='HKD',
                account_owner_id=test_owner
            )
            db.session.add(account2)
            db.session.flush()
            
            t = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-100.00,
                trans_account_id=account2.account_id,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(t)
            db.session.commit()
        
        response = logged_in_client.get(f'/?account_id={test_account}&tab=list-tab')
        assert response.status_code == 200

    def test_default_transaction_status(self, logged_in_client, app, test_owner, test_account, test_category):
        """手动添加的交易默认为未核对"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '200.00',
            'description': '新交易',
            'trans_date': '2026-01-15',
            'trans_time': '14:00'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            transaction = Transaction.query.filter_by(trans_desc='新交易').first()
            assert transaction is not None
            assert transaction.trans_status == TransactionStatus.UNVERIFIED

    def test_edit_transaction(self, logged_in_client, app, test_transaction, test_account, test_category):
        """编辑交易"""
        response = logged_in_client.post(f'/edit/{test_transaction}', data={
            'account_id': test_account,
            'category_id': test_category,
            'amount': '999.99',
            'description': '已编辑',
            'trans_date': '2026-06-01',
            'trans_time': '15:30'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            t = db.session.get(Transaction, test_transaction)
            assert t.trans_desc == '已编辑'
            assert abs(t.trans_amount) == 999.99

    def test_edit_transaction_datetime(self, logged_in_client, app, test_transaction, test_account, test_category):
        """编辑交易日期时间"""
        response = logged_in_client.post(f'/edit/{test_transaction}', data={
            'account_id': test_account,
            'category_id': test_category,
            'amount': '100.00',
            'description': '时间测试',
            'trans_date': '2026-12-25',
            'trans_time': '08:30'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            t = db.session.get(Transaction, test_transaction)
            assert t.trans_datetime.month == 12
            assert t.trans_datetime.day == 25
            assert t.trans_datetime.hour == 8
            assert t.trans_datetime.minute == 30

    def test_edit_nonexistent_transaction(self, logged_in_client, test_account, test_category):
        """编辑不存在的交易"""
        response = logged_in_client.post('/edit/99999', data={
            'account_id': test_account,
            'category_id': test_category,
            'amount': '100.00',
            'trans_date': '2026-01-01',
            'trans_time': '00:00'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_missing_required_fields(self, logged_in_client):
        """添加交易缺少必填字段"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': '',
            'category_id': '',
            'amount': '',
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_add_zero_amount(self, logged_in_client, app, test_account, test_category):
        """添加金额为0的交易"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '0',
            'trans_date': '2026-01-01',
            'trans_time': '00:00'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_tab_parameter_persists(self, logged_in_client, test_transaction):
        """操作后保持列表标签页"""
        response = logged_in_client.post(
            f'/status/{test_transaction}/VERIFIED',
            follow_redirects=True
        )
        assert response.status_code == 200
        assert 'tab=list-tab' in response.request.url

    def test_transaction_datetime_precision(self, logged_in_client, app, test_owner, test_account, test_category):
        """交易时间精确到分钟"""
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '50.00',
            'description': '精确时间测试',
            'trans_date': '2026-03-15',
            'trans_time': '14:45'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            t = Transaction.query.filter_by(trans_desc='精确时间测试').first()
            assert t is not None
            assert t.trans_datetime.hour == 14
            assert t.trans_datetime.minute == 45