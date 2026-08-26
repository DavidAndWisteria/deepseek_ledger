from datetime import datetime, timezone

import pytest
from app import db
from app.models import (
    Transaction, Account, Category, Owner, Family,
    CategoryType, AccountType, TransactionStatus, AccountBalance,
    TimeDeposit, DepositStatus
)
from sqlalchemy import select


def _create_deposit_account(app, test_owner, name='定期存款', atype=AccountType.TIME_DEPOSIT,
                            currency='HKD'):
    with app.app_context():
        account = Account(
            account_name=name,
            account_type=atype,
            account_custodian='银行',
            account_currency_name=currency,
            account_owner_id=test_owner
        )
        db.session.add(account)
        db.session.commit()
        return account.account_id


def _create_in_progress_deposit(app, account_id, amount=100000.0, currency='HKD',
                                rate=3.5, sub='2026-01-15', mat='2026-07-15'):
    with app.app_context():
        deposit = TimeDeposit(
            status=DepositStatus.IN_PROGRESS,
            account_id=account_id,
            deposit_currency_name=currency,
            amount=amount,
            interest_rate=rate,
            subscription_date=datetime.strptime(sub, '%Y-%m-%d').date(),
            maturity_date=datetime.strptime(mat, '%Y-%m-%d').date()
        )
        db.session.add(deposit)
        db.session.commit()
        return deposit.deposit_id


class TestDepositOpenFlow:
    """开立定期存款流程"""

    def test_transfer_to_deposit_redirects_open_flow(self, logged_in_client, app, test_owner,
                                                     test_account, test_category):
        """转账到定期存款账户 → 重定向到开立存款弹窗"""
        td_id = _create_deposit_account(app, test_owner)
        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': test_account,
            'to_account_id': td_id,
            'category_id': test_category,
            'amount': '100000.00',
            'to_amount': '100000.00',
            'description': '开立定存',
            'trans_date': '2026-01-15',
            'trans_time': '10:00'
        }, follow_redirects=False)
        assert response.status_code == 302
        assert 'deposit_flow=open' in response.headers['Location']
        assert f'deposit_account_id={td_id}' in response.headers['Location']
        assert 'deposit_amount=100000.0' in response.headers['Location']

        # 转账交易已创建
        with app.app_context():
            transfers = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc.contains('开立定存'))
            ).all()
            assert len(transfers) == 2

    def test_create_deposit_from_flow(self, logged_in_client, app, test_owner,
                                      test_account, test_category):
        """从开立弹窗提交 → 创建存款记录并关联转入交易"""
        td_id = _create_deposit_account(app, test_owner)
        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': test_account,
            'to_account_id': td_id,
            'category_id': test_category,
            'amount': '100000.00',
            'to_amount': '100000.00',
            'description': '开立定存',
            'trans_date': '2026-01-15',
            'trans_time': '10:00'
        }, follow_redirects=False)

        with app.app_context():
            trans_in = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '转入: 开立定存')
            ).first()
            trans_id = trans_in.trans_id

        response = logged_in_client.post('/deposits/create', data={
            'trans_id': trans_id,
            'account_id': td_id,
            'deposit_currency_name': 'HKD',
            'amount': '100000.00',
            'interest_rate': '3.5',
            'subscription_date': '2026-01-15',
            'maturity_date': '2026-07-15'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            deposit = db.session.scalars(
                select(TimeDeposit).where(TimeDeposit.account_id == td_id)
            ).first()
            assert deposit is not None
            assert deposit.status == DepositStatus.IN_PROGRESS
            assert deposit.amount == 100000.00
            assert deposit.interest_rate == 3.5
            assert deposit.deposit_currency_name == 'HKD'
            assert deposit.subscription_date.strftime('%Y-%m-%d') == '2026-01-15'
            assert deposit.maturity_date.strftime('%Y-%m-%d') == '2026-07-15'

            trans = db.session.get(Transaction, trans_id)
            assert trans.trans_deposit_id == deposit.deposit_id

    def test_create_deposit_validation(self, logged_in_client, app, test_owner,
                                       test_account, test_category):
        """缺少到期日期 → 校验失败并重开弹窗"""
        td_id = _create_deposit_account(app, test_owner)
        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': test_account,
            'to_account_id': td_id,
            'category_id': test_category,
            'amount': '100000.00',
            'to_amount': '100000.00',
            'description': '开立定存',
            'trans_date': '2026-01-15',
            'trans_time': '10:00'
        }, follow_redirects=False)

        response = logged_in_client.post('/deposits/create', data={
            'trans_id': '1',
            'account_id': td_id,
            'deposit_currency_name': 'HKD',
            'amount': '100000.00',
            'interest_rate': '3.5',
            'subscription_date': '2026-01-15',
            'maturity_date': ''
        }, follow_redirects=False)
        assert response.status_code == 302
        assert 'deposit_flow=open' in response.headers['Location']

        with app.app_context():
            deposits = db.session.scalars(
                select(TimeDeposit).where(TimeDeposit.account_id == td_id)
            ).all()
            assert len(deposits) == 0

    def test_manual_create_deposit(self, logged_in_client, app, test_owner):
        """存款页手动开立（无关联交易）"""
        td_id = _create_deposit_account(app, test_owner)
        response = logged_in_client.post('/deposits/create', data={
            'account_id': td_id,
            'deposit_currency_name': 'HKD',
            'amount': '50000.00',
            'interest_rate': '2.0',
            'subscription_date': '2026-03-01',
            'maturity_date': '2026-09-01'
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            deposit = db.session.scalars(
                select(TimeDeposit).where(TimeDeposit.account_id == td_id)
            ).first()
            assert deposit is not None
            assert deposit.amount == 50000.00


class TestDepositMatureFlow:
    """定期存款到期流程"""

    def test_transfer_from_deposit_redirects_mature_flow(self, logged_in_client, app, test_owner,
                                                         test_account, test_category):
        """转账从定期存款账户转出 → 重定向到到期登记弹窗"""
        td_id = _create_deposit_account(app, test_owner)
        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': td_id,
            'to_account_id': test_account,
            'category_id': test_category,
            'amount': '103500.00',
            'to_amount': '103500.00',
            'description': '定存到期',
            'trans_date': '2026-07-15',
            'trans_time': '10:00'
        }, follow_redirects=False)
        assert response.status_code == 302
        assert 'deposit_flow=mature' in response.headers['Location']
        assert f'deposit_account_id={td_id}' in response.headers['Location']

    def test_mature_deposit(self, logged_in_client, app, test_owner, test_account, test_category):
        """选择未到期存款并确认 → 状态改为已到期，自动计算收益"""
        td_id = _create_deposit_account(app, test_owner)
        deposit_id = _create_in_progress_deposit(app, td_id, amount=100000.0)

        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': td_id,
            'to_account_id': test_account,
            'category_id': test_category,
            'amount': '103500.00',
            'to_amount': '103500.00',
            'description': '定存到期',
            'trans_date': '2026-07-15',
            'trans_time': '10:00'
        }, follow_redirects=False)

        with app.app_context():
            trans_out = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '转出: 定存到期')
            ).first()
            trans_id = trans_out.trans_id

        response = logged_in_client.post(f'/deposits/{deposit_id}/mature', data={
            'trans_id': trans_id,
            'matured_amount': '103500.00',
            'matured_currency_name': 'HKD',
            'realized_pnl': ''
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            deposit = db.session.get(TimeDeposit, deposit_id)
            assert deposit.status == DepositStatus.MATURED
            assert deposit.matured_amount == 103500.00
            assert deposit.realized_pnl == 3500.00  # 103500 - 100000

            trans = db.session.get(Transaction, trans_id)
            assert trans.trans_deposit_id == deposit_id

    def test_mature_deposit_cld_non_hkd(self, logged_in_client, app, test_owner,
                                        test_account, test_category):
        """CLD 以非 HKD 到期 → realized_pnl 不填"""
        cld_id = _create_deposit_account(app, test_owner, name='CLD', atype=AccountType.CURRENCY_LINKED_DEPOSIT)
        deposit_id = _create_in_progress_deposit(app, cld_id, amount=100000.0, currency='USD')

        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': cld_id,
            'to_account_id': test_account,
            'category_id': test_category,
            'amount': '100500.00',
            'to_amount': '100500.00',
            'description': 'CLD到期',
            'trans_date': '2026-07-15',
            'trans_time': '10:00'
        }, follow_redirects=False)

        with app.app_context():
            trans_out = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '转出: CLD到期')
            ).first()
            trans_id = trans_out.trans_id

        response = logged_in_client.post(f'/deposits/{deposit_id}/mature', data={
            'trans_id': trans_id,
            'matured_amount': '100500.00',
            'matured_currency_name': 'HKD',
            'realized_pnl': ''
        }, follow_redirects=True)
        assert response.status_code == 200

        with app.app_context():
            deposit = db.session.get(TimeDeposit, deposit_id)
            assert deposit.status == DepositStatus.MATURED
            assert deposit.matured_amount == 100500.00
            # HKD 到期 → 仍自动计算收益（以基础货币）
            assert deposit.realized_pnl == 500.00

    def test_mature_deposit_validation(self, logged_in_client, app, test_owner,
                                       test_account, test_category):
        """到期金额为空 → 校验失败"""
        td_id = _create_deposit_account(app, test_owner)
        deposit_id = _create_in_progress_deposit(app, td_id)

        response = logged_in_client.post('/add', data={
            'trans_type': 'transfer',
            'account_id': td_id,
            'to_account_id': test_account,
            'category_id': test_category,
            'amount': '103500.00',
            'to_amount': '103500.00',
            'description': '定存到期',
            'trans_date': '2026-07-15',
            'trans_time': '10:00'
        }, follow_redirects=False)

        with app.app_context():
            trans_out = db.session.scalars(
                select(Transaction).where(Transaction.trans_desc == '转出: 定存到期')
            ).first()
            trans_id = trans_out.trans_id

        response = logged_in_client.post(f'/deposits/{deposit_id}/mature', data={
            'trans_id': trans_id,
            'matured_amount': '',
        }, follow_redirects=False)
        assert response.status_code == 302
        assert 'deposit_flow=mature' in response.headers['Location']

        with app.app_context():
            deposit = db.session.get(TimeDeposit, deposit_id)
            assert deposit.status == DepositStatus.IN_PROGRESS


class TestDepositList:
    """存款列表页面"""

    def test_deposits_page(self, logged_in_client, app, test_owner):
        response = logged_in_client.get('/deposits')
        assert response.status_code == 200
        assert '定期存款'.encode('utf-8') in response.data

    def test_deposits_page_after_create(self, logged_in_client, app, test_owner):
        td_id = _create_deposit_account(app, test_owner)
        _create_in_progress_deposit(app, td_id)
        response = logged_in_client.get('/deposits')
        assert response.status_code == 200
        assert '进行中'.encode('utf-8') in response.data
