import pytest
from app import db
from app.models import Account, AccountType, Owner
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
