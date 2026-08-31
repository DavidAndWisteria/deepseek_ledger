import pytest
from app import db
from app.models import Account, AccountType, Owner, Category
from sqlalchemy import select


class TestAccountRoutes:
    """账户路由测试"""

    def test_accounts_page(self, logged_in_client):
        response = logged_in_client.get('/accounts')
        assert response.status_code == 200

    def test_add_account(self, logged_in_client, app, test_owner):
        response = logged_in_client.post('/accounts/add', data={
            'account_name': '测试账户',
            'account_type': 'SAVING',
            'account_custodian': '测试银行',
            'currency': 'HKD',
            'account_create_date': '2026-01-01',
            'account_owner_id': test_owner
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            account = db.session.scalars(select(Account).where(Account.account_name == '测试账户')).first()
            assert account is not None
            assert account.account_type == AccountType.SAVING

    def test_add_account_empty_name(self, logged_in_client):
        response = logged_in_client.post('/accounts/add', data={
            'account_name': '',
            'account_type': 'SAVING',
            'account_custodian': '银行'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_edit_account(self, logged_in_client, app, test_account):
        response = logged_in_client.post(f'/accounts/{test_account}/edit', data={
            'account_name': '改名账户',
            'account_custodian': '新银行',
            'account_create_date': '',
        }, follow_redirects=True)
        assert response.status_code == 200
        
        with app.app_context():
            account = db.session.get(Account, test_account)
            assert account is not None
            assert account.account_name == '改名账户'

    def test_add_fund_account_with_isin(self, logged_in_client, app, test_owner):
        """基金账户新增 ISIN 代码，存储时自动转大写"""
        response = logged_in_client.post('/accounts/add', data={
            'account_name': '沪深300ETF',
            'account_type': 'FUND',
            'account_custodian': '基金公司',
            'currency': 'HKD',
            'account_isin': 'hk0000064689',
            'account_create_date': '2026-01-01',
            'account_owner_id': test_owner
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            account = db.session.scalars(
                select(Account).where(Account.account_name == '沪深300ETF')
            ).first()
            assert account is not None
            assert account.account_isin == 'HK0000064689'

    def test_edit_account_isin(self, logged_in_client, app, test_account):
        """编辑账户更新 ISIN 代码，清空时置为 None"""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.account_isin = 'HK0000064689'
            db.session.commit()

        response = logged_in_client.post(f'/accounts/{test_account}/edit', data={
            'account_name': '测试账户',
            'account_custodian': '测试银行',
            'account_isin': 'US4642874400',
            'account_create_date': '',
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            account = db.session.get(Account, test_account)
            assert account.account_isin == 'US4642874400'

        response = logged_in_client.post(f'/accounts/{test_account}/edit', data={
            'account_name': '测试账户',
            'account_custodian': '测试银行',
            'account_isin': '',
            'account_create_date': '',
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            account = db.session.get(Account, test_account)
            assert account.account_isin is None

    def test_delete_account(self, logged_in_client, app, test_account):
        """删除账户（通过确认接口）"""
        # 直接调用确认删除（无关联交易）
        response = logged_in_client.post(
            f'/accounts/{test_account}/delete/confirm',
            data={'action': 'delete'},
            follow_redirects=True
        )
        assert response.status_code == 200
        
        with app.app_context():
            account = db.session.get(Account, test_account)
            assert account is None

    def test_accounts_unauthenticated(self, client):
        response = client.get('/accounts', follow_redirects=True)
        assert '登录' in response.data.decode('utf-8')


class TestBalanceSheetTransfer:
    """资产负债表与交易页应包含转账交易"""

    def test_balance_includes_transfer_and_dashboard_shows_transfer(self, app, logged_in_client, test_owner):
        from datetime import date, timedelta, datetime, timezone
        from app.models import Transaction, TransactionStatus, CategoryType

        today = date.today()
        with app.app_context():
            bank = Account(
                account_name='银行户口', account_type=AccountType.SAVING,
                account_custodian='测试银行', account_currency_name='HKD',
                account_owner_id=test_owner, account_create_date=today - timedelta(days=60),
            )
            fund = Account(
                account_name='基金户口', account_type=AccountType.FUND,
                account_custodian='测试基金', account_currency_name='HKD',
                account_owner_id=test_owner, account_has_unit_ind=True,
                account_create_date=today - timedelta(days=60),
            )
            db.session.add_all([bank, fund])
            db.session.flush()
            transfer_cat = db.session.scalars(
                select(Category).where(Category.category_type == CategoryType.TRANSFER)
            ).first()
            if not transfer_cat:
                transfer_cat = Category(category_name='账户转账', category_class='转账',
                                        category_subclass='转账', category_type=CategoryType.TRANSFER)
                db.session.add(transfer_cat)
                db.session.flush()
            dt = datetime(today.year, today.month, today.day, 10, 0, tzinfo=timezone.utc)
            out_t = Transaction(trans_datetime=dt, trans_desc='转出: 买入基金',
                                trans_amount=-5000, trans_currency_name='HKD',
                                trans_account_id=bank.account_id,
                                trans_category_id=transfer_cat.category_id,
                                trans_owner_id=test_owner,
                                trans_status=TransactionStatus.UNVERIFIED)
            db.session.add(out_t)
            db.session.flush()
            in_t = Transaction(trans_datetime=dt, trans_desc='转入: 买入基金',
                               trans_amount=5000, trans_currency_name='HKD',
                               trans_account_id=fund.account_id,
                               trans_category_id=transfer_cat.category_id,
                               trans_owner_id=test_owner,
                               trans_status=TransactionStatus.UNVERIFIED,
                               trans_counter_id=out_t.trans_id,
                               trans_unit=50, trans_unit_price=100)
            db.session.add(in_t)
            db.session.flush()
            out_t.trans_counter_id = in_t.trans_id
            db.session.commit()
            fund_id = fund.account_id
            bank_id = bank.account_id

        start = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end = today.strftime('%Y-%m-%d')

        resp = logged_in_client.get(f'/accounts?tab=finance&start_date={start}&end_date={end}')
        assert resp.status_code == 200
        text = resp.get_data(as_text=True)
        assert f'data-id="{fund_id}"' in text, 'fund should appear in balance sheet'
        assert f'data-id="{bank_id}"' in text, 'bank should appear in balance sheet'

        resp2 = logged_in_client.get(
            f'/?account_id={fund_id}&start_date={start}&end_date={end}&from_accounts=1&tab=list-tab')
        assert resp2.status_code == 200
        text2 = resp2.get_data(as_text=True)
        assert '转入: 买入基金' in text2, 'fund transfer-in transaction should show on dashboard'
        assert '转账' in text2, 'transfer badge should be present'
