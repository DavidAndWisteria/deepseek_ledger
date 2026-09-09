from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from app import db
from app.models import (
    Transaction, Account, Category, Owner, Family,
    CategoryType, AccountType, TransactionStatus, AccountBalance
)
from sqlalchemy import select


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
            transaction = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '工资')
            ).first()
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
            transaction = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '午餐')
            ).first()
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
            transactions = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc.contains('还款'))
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
            assert transaction is not None
            assert transaction.trans_status == TransactionStatus.VERIFIED

    def test_update_status_to_unverified(self, logged_in_client, app, test_transaction):
        """更新交易状态回未核对"""
        with app.app_context():
            t = db.session.get(Transaction, test_transaction)
            assert t is not None
            t.trans_status = TransactionStatus.VERIFIED
            db.session.commit()
        
        response = logged_in_client.post(
            f'/status/{test_transaction}/UNVERIFIED',
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            transaction = db.session.get(Transaction, test_transaction)
            assert transaction is not None
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
            assert transaction is not None
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
                assert t is not None
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

    def test_dashboard_category_filter_clear_reverts(self, logged_in_client, app, test_owner, test_account, test_category):
        """修改分类筛选为"全部分类"时不应复原为上一次的分类（v0.3.12 回归测试）"""
        with app.app_context():
            other_cat = Category(
                category_name='交通',
                category_class='日常生活',
                category_subclass='出行',
                category_type=CategoryType.EXPENSE
            )
            db.session.add(other_cat)
            db.session.flush()

            t1 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='分类A交易',
                trans_amount=-111.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            t2 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='分类B交易',
                trans_amount=-222.00,
                trans_account_id=test_account,
                trans_category_id=other_cat.category_id,
                trans_owner_id=test_owner
            )
            db.session.add_all([t1, t2])
            db.session.commit()

        # 先按分类 A 筛选（写入 session 记忆）
        resp = logged_in_client.get(f'/?category_id={test_category}&tab=list-tab')
        assert resp.status_code == 200
        assert '分类A交易' in resp.get_data(as_text=True)
        assert '分类B交易' not in resp.get_data(as_text=True)

        # 再把分类改回"全部分类"（category_id 为空）并筛选
        resp2 = logged_in_client.get('/?category_id=&tab=list-tab')
        assert resp2.status_code == 200
        html2 = resp2.get_data(as_text=True)
        assert '分类A交易' in html2
        assert '分类B交易' in html2

    def test_dashboard_account_filter_clear_reverts(self, logged_in_client, app, test_owner, test_account, test_category):
        """账户筛选改回"全部账户"时不应复原为上一次的账户（v0.3.12 回归测试）"""
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

            t1 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='账户1交易',
                trans_amount=-333.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            t2 = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_desc='账户2交易',
                trans_amount=-444.00,
                trans_account_id=account2.account_id,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add_all([t1, t2])
            db.session.commit()

        resp = logged_in_client.get(f'/?account_id={test_account}&tab=list-tab')
        assert resp.status_code == 200
        assert '账户1交易' in resp.get_data(as_text=True)
        assert '账户2交易' not in resp.get_data(as_text=True)

        resp2 = logged_in_client.get('/?account_id=&tab=list-tab')
        assert resp2.status_code == 200
        html2 = resp2.get_data(as_text=True)
        assert '账户1交易' in html2
        assert '账户2交易' in html2

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
            transaction = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '新交易')
            ).first()
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
            assert t is not None
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
            assert t is not None
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
            t = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '精确时间测试')
            ).first()
            assert t is not None
            assert t.trans_datetime.hour == 14
            assert t.trans_datetime.minute == 45

    def test_batch_delete(self, logged_in_client, app, test_owner, test_account, test_category):
        """批量删除交易"""
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
            '/batch-delete',
            data={'trans_ids': ids},
            follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            for tid in ids:
                t = db.session.get(Transaction, tid)
                assert t is None

    def test_batch_delete_no_selection(self, logged_in_client):
        """空选择批量删除"""
        response = logged_in_client.post(
            '/batch-delete',
            data={},
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_batch_delete_transfer(self, logged_in_client, app, test_owner, test_account, test_category):
        """批量删除转账交易——同时删除配对记录"""
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

        logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': test_account,
            'to_account_id': to_account_id,
            'category_id': test_category,
            'amount': '1000.00',
            'description': '批量删除转账测试',
            'trans_date': '2026-06-01',
            'trans_time': '10:00'
        }, follow_redirects=True)

        with app.app_context():
            transfers = db.session.scalars(
                select(Transaction).where(
                    Transaction.trans_desc.contains('批量删除转账测试')
                )
            ).all()
            assert len(transfers) == 2
            ids = [t.trans_id for t in transfers]

        response = logged_in_client.post(
            '/batch-delete',
            data={'trans_ids': ids},
            follow_redirects=True
        )
        assert response.status_code == 200

        with app.app_context():
            for tid in ids:
                t = db.session.get(Transaction, tid)
                assert t is None

    def test_add_invalidates_balance(self, logged_in_client, app, test_account, test_category, test_owner):
        """添加交易后清除对应账户的缓存余额"""
        trans_date = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)

        with app.app_context():
            balance_before = AccountBalance(
                as_of_dt=trans_date.date(),
                account_id=test_account,
                account_balance=5000.00
            )
            db.session.add(balance_before)
            db.session.commit()

        logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': test_account,
            'category_id': test_category,
            'amount': '200.00',
            'description': '余额失效测试',
            'trans_date': trans_date.strftime('%Y-%m-%d'),
            'trans_time': '12:00'
        }, follow_redirects=True)

        with app.app_context():
            remaining = db.session.scalars(
                select(AccountBalance).where(
                    AccountBalance.account_id == test_account,
                    AccountBalance.as_of_dt == trans_date.date()
                )
            ).all()
            assert len(remaining) == 0

    def test_delete_invalidates_balance(self, logged_in_client, app, test_owner, test_account, test_category):
        """删除交易后清除对应账户的缓存余额"""
        with app.app_context():
            t = Transaction(
                trans_datetime=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
                trans_amount=-300.00,
                trans_desc='删除余额测试',
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(t)
            db.session.flush()

            balance = AccountBalance(
                as_of_dt=datetime(2026, 7, 15).date(),
                account_id=test_account,
                account_balance=10000.00
            )
            db.session.add(balance)
            db.session.commit()
            trans_id = t.trans_id

        logged_in_client.post(
            f'/delete/{trans_id}',
            follow_redirects=True
        )

        with app.app_context():
            remaining = db.session.scalars(
                select(AccountBalance).where(
                    AccountBalance.account_id == test_account,
                    AccountBalance.as_of_dt == datetime(2026, 7, 15).date()
                )
            ).all()
            assert len(remaining) == 0

    def test_edit_invalidates_balance(self, logged_in_client, app, test_owner, test_account, test_category):
        """编辑交易后清除缓存余额"""
        with app.app_context():
            t = Transaction(
                trans_datetime=datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc),
                trans_amount=-100.00,
                trans_desc='编辑余额测试',
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(t)
            db.session.flush()

            balance = AccountBalance(
                as_of_dt=datetime(2026, 8, 10).date(),
                account_id=test_account,
                account_balance=8000.00
            )
            db.session.add(balance)
            db.session.commit()
            trans_id = t.trans_id

        logged_in_client.post(f'/edit/{trans_id}', data={
            'account_id': test_account,
            'category_id': test_category,
            'amount': '500.00',
            'description': '编辑余额测试-已改',
            'trans_date': '2026-08-01',
            'trans_time': '10:00'
        }, follow_redirects=True)

        with app.app_context():
            remaining = db.session.scalars(
                select(AccountBalance).where(
                    AccountBalance.account_id == test_account,
                    AccountBalance.as_of_dt == datetime(2026, 8, 10).date()
                )
            ).all()
            assert len(remaining) == 0

    def test_edit_account_change_invalidates_both(self, logged_in_client, app, test_owner, test_account, test_category):
        """编辑交易更换账户后清除新旧账户的缓存余额"""
        with app.app_context():
            account2 = Account(
                account_name='账户B',
                account_type=AccountType.SAVING,
                account_custodian='测试银行',
                account_currency_name='HKD',
                account_owner_id=test_owner
            )
            db.session.add(account2)
            db.session.flush()

            t = Transaction(
                trans_datetime=datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc),
                trans_amount=200.00,
                trans_desc='换账户测试',
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(t)
            db.session.flush()

            balance_old = AccountBalance(
                as_of_dt=datetime(2026, 9, 10).date(),
                account_id=test_account,
                account_balance=3000.00
            )
            balance_new = AccountBalance(
                as_of_dt=datetime(2026, 9, 10).date(),
                account_id=account2.account_id,
                account_balance=7000.00
            )
            db.session.add_all([balance_old, balance_new])
            db.session.commit()
            trans_id = t.trans_id
            new_acct_id = account2.account_id

        logged_in_client.post(f'/edit/{trans_id}', data={
            'account_id': new_acct_id,
            'category_id': test_category,
            'amount': '200.00',
            'trans_date': '2026-09-01',
            'trans_time': '11:00'
        }, follow_redirects=True)

        with app.app_context():
            for acct_id in [test_account, new_acct_id]:
                remaining = db.session.scalars(
                    select(AccountBalance).where(
                        AccountBalance.account_id == acct_id,
                        AccountBalance.as_of_dt == datetime(2026, 9, 10).date()
                    )
                ).all()
                assert len(remaining) == 0, f"Account {acct_id} balance should be invalidated"

    def test_batch_delete_invalidates_balances(self, logged_in_client, app, test_owner, test_account, test_category):
        """批量删除后清除所有受影响账户的缓存余额"""
        with app.app_context():
            t1 = Transaction(
                trans_datetime=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
                trans_amount=-50.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            t2 = Transaction(
                trans_datetime=datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                trans_amount=-80.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add_all([t1, t2])
            db.session.flush()

            balance1 = AccountBalance(
                as_of_dt=datetime(2026, 10, 2).date(),
                account_id=test_account,
                account_balance=9000.00
            )
            balance2 = AccountBalance(
                as_of_dt=datetime(2026, 10, 10).date(),
                account_id=test_account,
                account_balance=8000.00
            )
            db.session.add_all([balance1, balance2])
            db.session.commit()
            ids = [t1.trans_id, t2.trans_id]

        logged_in_client.post(
            '/batch-delete',
            data={'trans_ids': ids},
            follow_redirects=True
        )

        with app.app_context():
            remaining = db.session.scalars(
                select(AccountBalance).where(AccountBalance.account_id == test_account)
            ).all()
            assert len(remaining) == 0

    def test_batch_delete_ignores_other_owners(self, logged_in_client, app, test_owner, test_account, test_category, test_family):
        """批量删除时不删除其他用户的交易"""
        with app.app_context():
            other_family = Family(family_name='另一个家庭')
            db.session.add(other_family)
            db.session.flush()

            other_owner = Owner(owner_name='其他用户', family_id=other_family.family_id)
            db.session.add(other_owner)
            db.session.flush()

            other_account = Account(
                account_name='他人账户',
                account_type=AccountType.SAVING,
                account_custodian='银行',
                account_owner_id=other_owner.owner_id
            )
            db.session.add(other_account)
            db.session.flush()

            my_t = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-100.00,
                trans_account_id=test_account,
                trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            other_t = Transaction(
                trans_datetime=datetime.now(timezone.utc),
                trans_amount=-200.00,
                trans_account_id=other_account.account_id,
                trans_category_id=test_category,
                trans_owner_id=other_owner.owner_id
            )
            db.session.add_all([my_t, other_t])
            db.session.commit()
            my_id = my_t.trans_id
            other_id = other_t.trans_id

        logged_in_client.post(
            '/batch-delete',
            data={'trans_ids': [my_id, other_id]},
            follow_redirects=True
        )

        with app.app_context():
            assert db.session.get(Transaction, my_id) is None
            other = db.session.get(Transaction, other_id)
            assert other is not None


class TestFundTransactionRoutes:
    """基金交易路由测试（含外币基金户口）"""

    def _create_fund_account(self, app, test_owner, currency):
        with app.app_context():
            account = Account(
                account_name=f'{currency}基金',
                account_type=AccountType.FUND,
                account_custodian='银行',
                account_currency_name=currency,
                account_owner_id=test_owner,
                account_has_unit_ind=True
            )
            db.session.add(account)
            db.session.commit()
            return account.account_id

    def test_add_hkd_fund_expense(self, logged_in_client, app, test_owner, test_category):
        """HKD 基金户口买入：单位=份额，单价=HKD"""
        fund_id = self._create_fund_account(app, test_owner, 'HKD')
        response = logged_in_client.post('/add', data={
            'trans_type': 'expense',
            'account_id': fund_id,
            'category_id': test_category,
            'currency': 'HKD',
            'amount': '1000.00',
            'unit': '50',
            'unit_price': '20',
            'trans_date': '2026-06-19',
            'trans_time': '12:00',
            'description': '买入HKD基金'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            t = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '买入HKD基金')
            ).first()
            assert t is not None
            assert t.trans_amount == -1000.00
            assert t.trans_unit == -50
            assert t.trans_unit_price == 20
            assert t.trans_unit_name is None
            assert t.is_fx is False

    def test_add_usd_fund_expense(self, logged_in_client, app, test_owner, test_category):
        """USD 基金户口买入：单价为 USD，金额按汇率换算 HKD"""
        fund_id = self._create_fund_account(app, test_owner, 'USD')
        with patch('app.routes.transactions.get_fx_rate_to_hkd', return_value=7.87):
            response = logged_in_client.post('/add', data={
                'trans_type': 'expense',
                'account_id': fund_id,
                'category_id': test_category,
                'currency': 'USD',
                'amount': '1050.00',
                'unit': '100',
                'unit_price': '10.5',
                'fx_rate': '0.127',
                'trans_date': '2026-06-19',
                'trans_time': '12:00',
                'description': '买入USD基金'
            }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            t = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '买入USD基金')
            ).first()
            assert t is not None
            assert t.trans_unit == -100          # 份额
            assert t.trans_unit_price == 10.5    # USD 单价
            assert t.trans_unit_name is None
            assert t.is_fx is False
            assert t.trans_currency_name == 'HKD'
            assert abs(t.trans_amount - (-8267.72)) < 1  # 1050 / 0.127

    def test_add_fund_transfer(self, logged_in_client, app, test_owner, test_category):
        """基金户口转账：转出记录保存份额与单价"""
        fund_id = self._create_fund_account(app, test_owner, 'HKD')
        with app.app_context():
            account2 = Account(
                account_name='基金转入',
                account_type=AccountType.SAVING,
                account_custodian='银行',
                account_currency_name='HKD',
                account_owner_id=test_owner
            )
            db.session.add(account2)
            db.session.commit()
            to_id = account2.account_id

        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': fund_id,
            'to_account_id': to_id,
            'category_id': test_category,
            'currency': 'HKD',
            'to_currency': 'HKD',
            'amount': '1000.00',
            'to_amount': '1000.00',
            'unit': '50',
            'unit_price': '20',
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '基金转账'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            out = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '转出: 基金转账')
            ).first()
            assert out is not None
            assert out.trans_unit == -50
            assert out.trans_unit_price == 20
            assert out.is_fx is False

    def test_edit_transfer_updates_both_sides(self, logged_in_client, app, test_owner, test_category):
        """编辑转账（点击转出侧）：同时更新转出+转入两侧账户、金额及基金份额/单价"""
        fund_id = self._create_fund_account(app, test_owner, 'HKD')
        with app.app_context():
            bank1 = Account(
                account_name='银行A', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            bank2 = Account(
                account_name='银行B', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            db.session.add_all([bank1, bank2])
            db.session.commit()
            bank1_id, bank2_id = bank1.account_id, bank2.account_id

        # 银行A → 基金 转账 1000
        resp = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': bank1_id,
            'to_account_id': fund_id,
            'category_id': test_category,
            'currency': 'HKD',
            'to_currency': 'HKD',
            'amount': '1000.00',
            'to_amount': '1000.00',
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '编辑转账测试'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            out_txn = db.session.scalars(select(Transaction).where(Transaction.trans_desc == '转出: 编辑转账测试')).first()
            in_txn = db.session.scalars(select(Transaction).where(Transaction.trans_desc == '转入: 编辑转账测试')).first()
            assert out_txn is not None and in_txn is not None
            out_id, in_id = out_txn.trans_id, in_txn.trans_id
            fund_db_id = in_txn.trans_account_id

        # 点击转出侧编辑：改银行B、金额1500，并给基金侧补上份额 75 @ 20
        resp = logged_in_client.post(f'/edit/{out_id}', data={
            'category_id': test_category,
            'out_account_id': bank2_id,
            'out_amount': '1500.00',
            'out_currency': 'HKD',
            'in_account_id': fund_db_id,
            'in_amount': '1500.00',
            'in_currency': 'HKD',
            'in_unit': '75',
            'in_unit_price': '20',
            'trans_date': '2026-06-21',
            'trans_time': '09:30',
            'description': '已编辑转账'
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '交易更新成功'.encode('utf-8') in resp.data

        with app.app_context():
            out = db.session.get(Transaction, out_id)
            inn = db.session.get(Transaction, in_id)
            assert out.trans_account_id == bank2_id
            assert out.trans_amount == -1500.00
            assert out.trans_unit is None
            assert inn.trans_account_id == fund_db_id
            assert inn.trans_amount == 1500.00
            assert inn.trans_unit == 75
            assert inn.trans_unit_price == 20
            assert inn.trans_desc == '已编辑转账'
            assert out.trans_desc == '已编辑转账'
            assert out.trans_datetime.day == 21
            assert out.trans_category_id == test_category

    def test_edit_transfer_from_in_side(self, logged_in_client, app, test_owner, test_category):
        """编辑转账（点击转入侧）：从转入侧提交同样更新两侧金额"""
        with app.app_context():
            acc1 = Account(
                account_name='账户1', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            acc2 = Account(
                account_name='账户2', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            db.session.add_all([acc1, acc2])
            db.session.commit()
            acc1_id, acc2_id = acc1.account_id, acc2.account_id

        resp = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': acc1_id,
            'to_account_id': acc2_id,
            'category_id': test_category,
            'currency': 'HKD',
            'to_currency': 'HKD',
            'amount': '1000.00',
            'to_amount': '1000.00',
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '转入侧编辑'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            out_txn = db.session.scalars(select(Transaction).where(Transaction.trans_desc == '转出: 转入侧编辑')).first()
            in_txn = db.session.scalars(select(Transaction).where(Transaction.trans_desc == '转入: 转入侧编辑')).first()
            assert out_txn is not None and in_txn is not None
            out_id, in_id = out_txn.trans_id, in_txn.trans_id

        # 点击转入侧编辑，仅改金额
        resp = logged_in_client.post(f'/edit/{in_id}', data={
            'category_id': test_category,
            'out_account_id': acc1_id,
            'out_amount': '1234.00',
            'out_currency': 'HKD',
            'in_account_id': acc2_id,
            'in_amount': '1234.00',
            'in_currency': 'HKD',
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '转入侧编辑'
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '交易更新成功'.encode('utf-8') in resp.data

        with app.app_context():
            out = db.session.get(Transaction, out_id)
            inn = db.session.get(Transaction, in_id)
            assert out.trans_amount == -1234.00
            assert inn.trans_amount == 1234.00
            assert out.trans_account_id == acc1_id
            assert inn.trans_account_id == acc2_id

    def test_edit_transfer_missing_side_fails(self, logged_in_client, app, test_owner, test_category):
        """编辑转账缺少任一侧账户/金额 → 提示请填写完整信息"""
        with app.app_context():
            acc1 = Account(
                account_name='账户1', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            acc2 = Account(
                account_name='账户2', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            db.session.add_all([acc1, acc2])
            db.session.commit()
            acc1_id, acc2_id = acc1.account_id, acc2.account_id

        resp = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': acc1_id,
            'to_account_id': acc2_id,
            'category_id': test_category,
            'currency': 'HKD',
            'to_currency': 'HKD',
            'amount': '1000.00',
            'to_amount': '1000.00',
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '缺失测试'
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            out_id = db.session.scalars(select(Transaction).where(Transaction.trans_desc == '转出: 缺失测试')).first().trans_id

        resp = logged_in_client.post(f'/edit/{out_id}', data={
            'category_id': test_category,
            'out_account_id': acc1_id,
            'out_amount': '1000.00',
            'out_currency': 'HKD',
            # 缺少转入侧
            'trans_date': '2026-06-20',
            'trans_time': '12:00',
            'description': '缺失测试'
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '请填写完整信息'.encode('utf-8') in resp.data

    def test_dashboard_transfer_row_contains_both_sides(self, logged_in_client, app, test_owner, test_category):
        """列表页：转账交易的详情数据同时携带转出/转入两侧（含基金份额与单价）"""
        fund_id = self._create_fund_account(app, test_owner, 'HKD')
        with app.app_context():
            bank = Account(
                account_name='恒生卡', account_type=AccountType.SAVING,
                account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner
            )
            db.session.add(bank)
            db.session.commit()
            bank_id = bank.account_id

        # 银行 → 基金 转账，并手动给基金侧补份额/单价（模拟基金购买导入后的状态）
        with app.app_context():
            out = Transaction(
                trans_datetime=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
                trans_desc='转出: 基金购买', trans_amount=-1000.00,
                trans_currency_name='HKD', trans_account_id=bank_id,
                trans_category_id=test_category, trans_owner_id=test_owner,
                trans_status=TransactionStatus.UNVERIFIED
            )
            db.session.add(out)
            db.session.flush()
            inn = Transaction(
                trans_datetime=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
                trans_desc='转入: 基金购买', trans_amount=1000.00,
                trans_currency_name='HKD', trans_account_id=fund_id,
                trans_category_id=test_category, trans_owner_id=test_owner,
                trans_counter_id=out.trans_id, trans_status=TransactionStatus.UNVERIFIED,
                trans_unit=50.0, trans_unit_price=20.0
            )
            db.session.add(inn)
            db.session.flush()
            out.trans_counter_id = inn.trans_id
            db.session.commit()

        resp = logged_in_client.get('/?start_date=2026-06-01&end_date=2026-06-30&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # 转出/转入两侧数据均出现在详情按钮中，且基金份额与单价包含在内
        assert 'out: {id:' in html
        assert 'in: {id:' in html
        assert 'unit: 50' in html
        assert 'unitPrice: 20' in html
        assert '基金购买'.encode('utf-8') in resp.data

    def test_dashboard_daily_subtotal_net(self, logged_in_client, app, test_owner, test_account, test_category):
        """列表页每日小计栏显示当日总结余：收入-支出+转入-转出（含转账/特殊）"""
        with app.app_context():
            other = Account(
                account_name='另一个账户', account_type=AccountType.SAVING,
                account_custodian='测试券商', account_currency_name='HKD',
                account_owner_id=test_owner
            )
            db.session.add(other)
            db.session.flush()
            other_id = other.account_id

            income_cat = Category(
                category_name='工资', category_class='收入',
                category_subclass='薪酬', category_type=CategoryType.INCOME
            )
            transfer_cat = Category(
                category_name='划转', category_class='资产变动',
                category_subclass='内部划转', category_type=CategoryType.TRANSFER
            )
            db.session.add_all([income_cat, transfer_cat])
            db.session.flush()

            day = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)
            income = Transaction(
                trans_datetime=day, trans_desc='工资收入', trans_amount=100.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=income_cat.category_id, trans_owner_id=test_owner
            )
            expense = Transaction(
                trans_datetime=day, trans_desc='午饭', trans_amount=-30.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            db.session.add_all([income, expense])
            db.session.flush()
            out = Transaction(
                trans_datetime=day, trans_desc='转出: 划转', trans_amount=-50.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=transfer_cat.category_id, trans_owner_id=test_owner
            )
            inn = Transaction(
                trans_datetime=day, trans_desc='转入: 划转', trans_amount=50.00,
                trans_currency_name='HKD', trans_account_id=other_id,
                trans_category_id=transfer_cat.category_id, trans_owner_id=test_owner
            )
            db.session.add_all([out, inn])
            db.session.flush()
            out.trans_counter_id = inn.trans_id
            inn.trans_counter_id = out.trans_id
            db.session.commit()

        resp = logged_in_client.get('/?start_date=2026-06-15&end_date=2026-06-15&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '📥 收入: $100.00' in html
        assert '📤 支出: $30.00' in html
        # 总结余 = 100 - 30 - 50(转出) + 50(转入) = 70
        assert '总结余: $70.00' in html

    def test_dashboard_daily_subtotal_net_single_account(self, logged_in_client, app, test_owner, test_account, test_category):
        """按单账户筛选时，转账仅计算该账户一侧：总结余应体现转出"""
        with app.app_context():
            other = Account(
                account_name='另一个账户', account_type=AccountType.SAVING,
                account_custodian='测试券商', account_currency_name='HKD',
                account_owner_id=test_owner
            )
            db.session.add(other)
            db.session.flush()
            other_id = other.account_id

            day = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
            income = Transaction(
                trans_datetime=day, trans_desc='当日收入', trans_amount=200.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            out = Transaction(
                trans_datetime=day, trans_desc='转出: 划走', trans_amount=-80.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            inn = Transaction(
                trans_datetime=day, trans_desc='转入: 划走', trans_amount=80.00,
                trans_currency_name='HKD', trans_account_id=other_id,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            db.session.add_all([income, out, inn])
            db.session.flush()
            out.trans_counter_id = inn.trans_id
            inn.trans_counter_id = out.trans_id
            db.session.commit()

        resp = logged_in_client.get(f'/?start_date=2026-06-16&end_date=2026-06-16&tab=list-tab&account_id={test_account}')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # 只显示 test_account 一侧：200 - 80(转出) = 120（另一账户的转入 +80 不在筛选内）
        assert '总结余: $120.00' in html

    def test_dashboard_daily_subtotal_fx_rerate(self, logged_in_client, app, test_owner, test_account, test_category):
        """外币交易按“交易当日”汇率折算 HKD 计入每日小计与顶部卡片（不与录入时汇率混用）"""
        with app.app_context():
            day = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
            # USD 支出 100：录入时按 7.0 折算，trans_amount=-700、HKD 口径，但原始币金额/币种保留在 fx 字段
            usd_expense = Transaction(
                trans_datetime=day, trans_desc='USD支出', trans_amount=-700.00,
                trans_currency_name='HKD', trans_fx_amount=-100.00,
                trans_fx_currency_name='USD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            # HKD 收入 50
            income = Transaction(
                trans_datetime=day, trans_desc='HKD收入', trans_amount=50.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            db.session.add_all([usd_expense, income])
            db.session.commit()

        with patch('app.routes.transactions.get_fx_rate_to_hkd', return_value=7.8):
            resp = logged_in_client.get('/?start_date=2026-06-18&end_date=2026-06-18&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # 当日汇率口径：支出=100*7.8=780，收入=50，净=-730（而非按录入 7.0 折算的 700）
        assert '📥 收入: $50.00' in html
        assert '📤 支出: $780.00' in html
        assert '总结余: $-730.00' in html
        # 顶部卡片同口径
        assert '📤 总支出' in html
        assert '$-730.00' in html  # 净收入卡片
        assert html.count('$780.00') >= 2  # 顶部总支出 + 每日支出小计

    def test_dashboard_daily_subtotal_fx_rate_unavailable_fallback(self, logged_in_client, app, test_owner, test_account, test_category):
        """取不到当日汇率时回退到已存金额，避免外币被按 1.0 误算"""
        with app.app_context():
            day = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
            usd_expense = Transaction(
                trans_datetime=day, trans_desc='USD支出', trans_amount=-700.00,
                trans_currency_name='HKD', trans_fx_amount=-100.00,
                trans_fx_currency_name='USD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            db.session.add(usd_expense)
            db.session.commit()

        # get_fx_rate_to_hkd 失败时返回 1.0，_fx_day_rate 应识别为“取不到”并回退到已存 HKD 金额
        with patch('app.routes.transactions.get_fx_rate_to_hkd', return_value=1.0):
            resp = logged_in_client.get('/?start_date=2026-06-18&end_date=2026-06-18&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '📤 支出: $700.00' in html
        assert '总结余: $-700.00' in html

    def test_dashboard_daily_subtotal_fx_transfer(self, logged_in_client, app, test_owner, test_account, test_category):
        """跨币种转账：两侧均按当日汇率折算后再计入结余，应相互抵消为 0（不再把原币直接相加）"""
        with app.app_context():
            other = Account(
                account_name='USD账户', account_type=AccountType.SAVING,
                account_custodian='券商', account_currency_name='USD',
                account_owner_id=test_owner
            )
            db.session.add(other)
            db.session.flush()
            other_id = other.account_id

            day = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
            out = Transaction(
                trans_datetime=day, trans_desc='转出: 划转', trans_amount=-800.00,
                trans_currency_name='HKD', trans_account_id=test_account,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            inn = Transaction(
                trans_datetime=day, trans_desc='转入: 划转', trans_amount=100.00,
                trans_currency_name='USD', trans_account_id=other_id,
                trans_category_id=test_category, trans_owner_id=test_owner
            )
            db.session.add_all([out, inn])
            db.session.flush()
            out.trans_counter_id = inn.trans_id
            inn.trans_counter_id = out.trans_id
            db.session.commit()

        with patch('app.routes.transactions.get_fx_rate_to_hkd', return_value=8.0):
            resp = logged_in_client.get('/?start_date=2026-06-18&end_date=2026-06-18&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # 转出 -800 HKD + 转入 100 USD × 8.0 = 800 HKD → 净变动为 0
        assert '总结余: $0.00' in html

    def test_dashboard_daily_subtotal_fx_fund_units(self, logged_in_client, app, test_owner, test_account, test_category):
        """外币基金（份额×单价为原币）也按当日汇率折算计入支出/总结余"""
        with app.app_context():
            fund = Account(
                account_name='USD基金', account_type=AccountType.FUND,
                account_custodian='基金公司', account_currency_name='USD',
                account_owner_id=test_owner, account_has_unit_ind=True
            )
            db.session.add(fund)
            db.session.flush()
            fund_id = fund.account_id

            day = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
            # 录入当时折算：trans_amount=-8190 HKD；原币为 100 份 × 10.5 USD = -1050 USD
            purchase = Transaction(
                trans_datetime=day, trans_desc='买入USD基金', trans_amount=-8190.00,
                trans_currency_name='HKD', trans_unit=-100.00, trans_unit_price=10.5,
                trans_account_id=fund_id, trans_category_id=test_category,
                trans_owner_id=test_owner
            )
            db.session.add(purchase)
            db.session.commit()

        with patch('app.routes.transactions.get_fx_rate_to_hkd', return_value=8.0):
            resp = logged_in_client.get('/?start_date=2026-06-18&end_date=2026-06-18&tab=list-tab')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # -1050 USD × 8.0 = -8400 HKD（而非录入口径的 8190）
        assert '📤 支出: $8,400.00' in html
        assert '总结余: $-8,400.00' in html

    def test_dashboard_multiselect_status(self, logged_in_client, app, test_owner, test_account, test_category):
        """状态多选筛选：多个状态取并集，未选中的状态被排除"""
        with app.app_context():
            day = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
            rows = [
                ('未核对A', -10001.00, TransactionStatus.UNVERIFIED),
                ('已核对B', -20002.00, TransactionStatus.VERIFIED),
                ('疑问C', -40004.00, TransactionStatus.FLAGGED),
            ]
            for desc, amt, st in rows:
                db.session.add(Transaction(
                    trans_datetime=day, trans_desc=desc, trans_amount=amt,
                    trans_currency_name='HKD', trans_account_id=test_account,
                    trans_category_id=test_category, trans_owner_id=test_owner,
                    trans_status=st
                ))
            db.session.commit()

        resp = logged_in_client.get(
            '/?start_date=2026-09-05&end_date=2026-09-05&tab=list-tab&status=UNVERIFIED&status=VERIFIED'
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '-10,001.00' in html
        assert '-20,002.00' in html
        assert '-40,004.00' not in html

    def test_dashboard_multiselect_category(self, logged_in_client, app, test_owner, test_account, test_category):
        """分类多选筛选：多个分类取并集"""
        with app.app_context():
            cat_a = Category(category_name='餐饮A', category_class='日常生活', category_subclass='饮食', category_type=CategoryType.EXPENSE)
            cat_b = Category(category_name='交通B', category_class='日常生活', category_subclass='出行', category_type=CategoryType.EXPENSE)
            cat_c = Category(category_name='购物C', category_class='日常生活', category_subclass='购物', category_type=CategoryType.EXPENSE)
            db.session.add_all([cat_a, cat_b, cat_c])
            db.session.flush()

            day = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
            specs = [
                (-11001.00, cat_a.category_id),
                (-22002.00, cat_b.category_id),
                (-55005.00, cat_c.category_id),
            ]
            for amt, cid in specs:
                db.session.add(Transaction(
                    trans_datetime=day, trans_desc='多分类', trans_amount=amt,
                    trans_currency_name='HKD', trans_account_id=test_account,
                    trans_category_id=cid, trans_owner_id=test_owner
                ))
            db.session.commit()
            cid_a, cid_b, cid_c = cat_a.category_id, cat_b.category_id, cat_c.category_id

        resp = logged_in_client.get(
            f'/?start_date=2026-09-05&end_date=2026-09-05&tab=list-tab&category_id={cid_a}&category_id={cid_b}'
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '-11,001.00' in html
        assert '-22,002.00' in html
        assert '-55,005.00' not in html

    def test_dashboard_multiselect_account(self, logged_in_client, app, test_owner, test_account, test_category):
        """账户多选筛选：多个账户取并集"""
        with app.app_context():
            acc_b = Account(account_name='账户B', account_type=AccountType.SAVING, account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner)
            acc_c = Account(account_name='账户C', account_type=AccountType.SAVING, account_custodian='银行', account_currency_name='HKD', account_owner_id=test_owner)
            db.session.add_all([acc_b, acc_c])
            db.session.flush()

            day = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
            specs = [
                (-12001.00, test_account),
                (-23002.00, acc_b.account_id),
                (-66006.00, acc_c.account_id),
            ]
            for amt, aid in specs:
                db.session.add(Transaction(
                    trans_datetime=day, trans_desc='多账户', trans_amount=amt,
                    trans_currency_name='HKD', trans_account_id=aid,
                    trans_category_id=test_category, trans_owner_id=test_owner
                ))
            db.session.commit()
            bid, cid = acc_b.account_id, acc_c.account_id

        resp = logged_in_client.get(
            f'/?start_date=2026-09-05&end_date=2026-09-05&tab=list-tab&account_id={test_account}&account_id={bid}'
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '-12,001.00' in html
        assert '-23,002.00' in html
        assert '-66,006.00' not in html