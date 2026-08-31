import io

import pytest
from app import db
from app.models import (
    Account, Category, CategoryType, User, Transaction, AccountType, TransactionStatus
)
from app.services.import_service import ImportService
from sqlalchemy import select

FUND_CSV = """hs_code,purchase_date,unit,purchase_cost,currency,purchase_unit_cost,purchase_bank
"U44976",2020-07-02,181.494,199999.13,"HKD",1101.96,"Hang Seng"
"U44564",2020-11-10,3904.382,50015.13,"HKD",12.81,"Hang Seng"
"""

FUND_CSV_NO_UNIT = """hs_code,purchase_date,unit,purchase_cost,currency,purchase_unit_cost,purchase_bank
"U44976",2020-07-02,,1000.00,"HKD",,"Hang Seng"
"""


def _create_fund_account(app, test_owner, name='沪深300ETF', alias='U44976'):
    with app.app_context():
        account = Account(
            account_name=name,
            account_other_name=alias,
            account_type=AccountType.FUND,
            account_custodian='基金公司',
            account_currency_name='HKD',
            account_owner_id=test_owner,
            account_has_unit_ind=True
        )
        db.session.add(account)
        db.session.commit()
        return account.account_id


def _create_fund_accounts(app, test_owner):
    """创建 CSV 中两个 hs_code 对应的基金账户"""
    _create_fund_account(app, test_owner, name='沪深300ETF', alias='U44976')
    _create_fund_account(app, test_owner, name='联博美国债券', alias='U44564')


def _create_bank_account(app, test_owner, name='恒生卡', custodian='Hang Seng'):
    with app.app_context():
        account = Account(
            account_name=name,
            account_type=AccountType.SAVING,
            account_custodian=custodian,
            account_currency_name='HKD',
            account_owner_id=test_owner
        )
        db.session.add(account)
        db.session.commit()
        return account.account_id


class TestImportFundPurchase:
    """基金购买交易导入"""

    def _service(self, app, test_user):
        with app.app_context():
            user = db.session.get(User, test_user)
            return ImportService(user)

    def test_import_fund_purchase(self, app, test_user, test_owner):
        """导入基金购买 → 生成银行 → 基金转账，基金侧记录份额与单价"""
        fund_id = _create_fund_account(app, test_owner)
        fund2_id = _create_fund_account(app, test_owner, name='联博美国债券', alias='U44564')
        bank_id = _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV)

        assert result['success'] == 2
        assert result['failed'] == 0

        with app.app_context():
            trans_in = db.session.scalars(
                select(Transaction).where(
                    Transaction.trans_account_id == fund_id,
                    Transaction.trans_amount == 199999.13
                )
            ).first()
            assert trans_in is not None
            assert trans_in.is_transfer() is True
            assert trans_in.trans_unit == 181.494
            assert trans_in.trans_unit_price == 1101.96
            assert trans_in.trans_status == TransactionStatus.UNVERIFIED

            trans_out = db.session.get(Transaction, trans_in.trans_counter_id)
            assert trans_out is not None
            assert trans_out.trans_account_id == bank_id
            assert trans_out.trans_amount == -199999.13

            # 第二行
            trans_in2 = db.session.scalars(
                select(Transaction).where(
                    Transaction.trans_account_id == fund2_id,
                    Transaction.trans_amount == 50015.13
                )
            ).first()
            assert trans_in2 is not None
            assert trans_in2.trans_unit == 3904.382
            assert trans_in2.trans_unit_price == 12.81

    def test_import_invalidates_stale_balance_cache(self, app, test_user, test_owner, logged_in_client):
        """导入基金购买后应使日终余额缓存失效，余额包含转账交易（不再显示旧的 0 余额）"""
        from datetime import date
        from app.models import AccountBalance

        with app.app_context():
            fund = Account(
                account_name='沪深300ETF', account_other_name='U44976',
                account_type=AccountType.FUND, account_custodian='基金公司',
                account_currency_name='HKD', account_owner_id=test_owner,
                account_has_unit_ind=True, account_create_date=date(2019, 1, 1),
            )
            _create_bank_account(app, test_owner)
            db.session.add(fund)
            db.session.commit()
            fund_id = fund.account_id

        # 1) 先查看资产负债表 → 生成 0 余额缓存（模拟导入前已缓存）
        resp = logged_in_client.get('/accounts?tab=finance&start_date=2020-01-01&end_date=2020-12-31')
        assert resp.status_code == 200
        with app.app_context():
            cached = db.session.scalars(
                select(AccountBalance).where(AccountBalance.account_id == fund_id)
            ).all()
            assert cached, 'cache should have been created'
            assert all(r.account_balance == 0 for r in cached)

        # 2) 导入基金购买 → 生成转账交易，缓存应被清除
        service = self._service(app, test_user)
        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV)
        assert result['success'] == 1

        # 3) 再次查看资产负债表 → 缓存重算，余额包含转账
        resp = logged_in_client.get('/accounts?tab=finance&start_date=2020-01-01&end_date=2020-12-31')
        assert resp.status_code == 200
        with app.app_context():
            cached = db.session.scalars(
                select(AccountBalance).where(AccountBalance.account_id == fund_id)
            ).all()
            assert cached, 'cache should exist after re-view'
            assert any(r.account_balance == 199999.13 for r in cached), \
                f'fund balance should be 199999.13, got {[r.account_balance for r in cached]}'

    def test_import_fund_purchase_no_unit(self, app, test_user, test_owner):
        """无份额/单价 → 转账正常生成，不记录单位"""
        fund_id = _create_fund_account(app, test_owner)
        _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV_NO_UNIT)

        assert result['success'] == 1

        with app.app_context():
            trans_in = db.session.scalars(
                select(Transaction).where(
                    Transaction.trans_account_id == fund_id,
                    Transaction.trans_amount == 1000.00
                )
            ).first()
            assert trans_in is not None
            assert trans_in.trans_unit is None
            assert trans_in.trans_unit_price is None

    def test_import_fund_purchase_missing_fund(self, app, test_user, test_owner):
        """hs_code 未匹配基金账户且未手动处理 → 跳过（未处理），不计入失败"""
        _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV)

        assert result['success'] == 0
        assert result['skipped'] == 2
        assert result['failed'] == 0

        with app.app_context():
            assert db.session.scalars(select(Transaction)).all() == []

    def test_import_fund_purchase_missing_bank(self, app, test_user, test_owner):
        """purchase_bank 未匹配银行账户且未手动处理 → 跳过（未处理），不计入失败"""
        _create_fund_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV)

        assert result['success'] == 0
        assert result['skipped'] == 2
        assert result['failed'] == 0

    def test_import_fund_purchase_manual_unresolvable_fails(self, app, test_user, test_owner):
        """已手动指定账户但 fund 仍无法解析 → 仍计为失败（确认导入语义）"""
        _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(
                FUND_CSV,
                manual_mappings={1: {'bank_account_id': 999999}},
            )

        assert result['success'] == 0
        assert result['skipped'] == 1   # 第 2 行未手动处理 → 跳过
        assert result['failed'] == 1    # 第 1 行手动指定但 fund 无法解析 → 失败

    def test_import_fund_purchase_dedup(self, app, test_user, test_owner):
        """重复导入同一文件 → 第二遍全部跳过"""
        _create_fund_accounts(app, test_owner)
        _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            r1 = service.import_fund_purchases_csv(FUND_CSV)
            r2 = service.import_fund_purchases_csv(FUND_CSV)

        assert r1['success'] == 2
        assert r2['success'] == 0
        assert r2['skipped'] == 2

    def test_fund_import_route(self, logged_in_client, app, test_owner):
        """导入路由：上传基金 CSV → 预览 → 确认导入"""
        _create_fund_accounts(app, test_owner)
        _create_bank_account(app, test_owner)

        # 上传预览
        resp = logged_in_client.post(
            '/import/fund-purchases/upload',
            data={'file': (io.BytesIO(FUND_CSV.encode('utf-8')), 'fund.csv')},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert '基金购买导入预览'.encode('utf-8') in resp.data
        assert '自动匹配'.encode('utf-8') in resp.data

        # 确认导入
        resp = logged_in_client.post('/import/fund-purchases/confirm', follow_redirects=True)
        assert resp.status_code == 200
        assert '基金购买导入完成：成功 2'.encode('utf-8') in resp.data

    def test_fund_import_manual_mapping_route(self, logged_in_client, app, test_owner):
        """银行名称无法自动匹配（恒生銀行 vs Hang Seng）→ 预览需处理，手动选择银行后导入"""
        _create_fund_accounts(app, test_owner)
        bank_id = _create_bank_account(app, test_owner, name='恒生卡', custodian='恒生銀行')

        resp = logged_in_client.post(
            '/import/fund-purchases/upload',
            data={'file': (io.BytesIO(FUND_CSV.encode('utf-8')), 'fund.csv')},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert '需处理'.encode('utf-8') in resp.data

        resp = logged_in_client.post('/import/fund-purchases/confirm', data={
            'fund_bank_1': bank_id,
            'fund_bank_2': bank_id,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '基金购买导入完成：成功 2'.encode('utf-8') in resp.data

        with app.app_context():
            txns = db.session.scalars(select(Transaction)).all()
            assert len(txns) == 4  # 两笔转账 = 4 条记录

    def test_fund_import_skip_unmatched_service(self, app, test_user, test_owner):
        """服务层：skip_unmatched=True 时未匹配的行被跳过而非失败"""
        _create_fund_account(app, test_owner)  # 仅 U44976
        _create_bank_account(app, test_owner)
        service = self._service(app, test_user)

        with app.app_context():
            result = service.import_fund_purchases_csv(FUND_CSV, skip_unmatched=True)

        assert result['success'] == 1
        assert result['skipped'] == 1
        assert result['failed'] == 0

    def test_fund_import_unconfigured_rows_skipped_not_failed(self, app, test_user, test_owner):
        """只手动处理一笔、其余留空 → 已存在/未处理均算跳过，不再出现大批失败"""
        _create_fund_accounts(app, test_owner)
        bank_id = _create_bank_account(app, test_owner, name='恒生卡', custodian='恒生銀行')  # 英文 Hang Seng 无法自动匹配
        service = self._service(app, test_user)

        with app.app_context():
            # 第一次：两笔都手动选银行 → 全部导入
            r1 = service.import_fund_purchases_csv(FUND_CSV, manual_mappings={
                1: {'bank_account_id': bank_id},
                2: {'bank_account_id': bank_id},
            })
            assert r1['success'] == 2
            assert r1['skipped'] == 0
            assert r1['failed'] == 0

            # 第二次（用户报告场景）：只给第 1 行选银行，其余留空
            r2 = service.import_fund_purchases_csv(FUND_CSV, manual_mappings={
                1: {'bank_account_id': bank_id},
            })
            assert r2['success'] == 0
            assert r2['skipped'] == 2
            assert r2['failed'] == 0

        with app.app_context():
            reasons = [d['reason'] for d in r2['details'] if d['status'] == 'skipped']
            assert '已存在相同交易' in reasons  # 第 1 行重复导入
            assert '未处理（银行账户未匹配）' in reasons  # 第 2 行留空
            # 仍只有 4 条交易（两笔转账），没有因重导产生重复
            assert len(db.session.scalars(select(Transaction)).all()) == 4

    def test_fund_import_confirm_route_skip_breakdown(self, logged_in_client, app, test_owner):
        """路由：确认导入 flash 提示包含跳过原因细分（已存在 / 未处理）"""
        _create_fund_accounts(app, test_owner)
        _create_bank_account(app, test_owner)

        def _upload():
            return logged_in_client.post(
                '/import/fund-purchases/upload',
                data={'file': (io.BytesIO(FUND_CSV.encode('utf-8')), 'fund.csv')},
                content_type='multipart/form-data',
                follow_redirects=True
            )

        # 第一次：上传 → 确认，两笔全部导入
        resp = _upload()
        assert resp.status_code == 200
        resp = logged_in_client.post('/import/fund-purchases/confirm', follow_redirects=True)
        assert resp.status_code == 200
        assert '成功 2'.encode('utf-8') in resp.data

        # 第二次：重新上传 → 确认，两笔均已存在 → 全部跳过
        resp = _upload()
        assert resp.status_code == 200
        resp = logged_in_client.post('/import/fund-purchases/confirm', follow_redirects=True)
        assert resp.status_code == 200
        assert '跳过 2'.encode('utf-8') in resp.data
        assert '已存在 2'.encode('utf-8') in resp.data

    def test_fund_import_custom_category(self, logged_in_client, app, test_owner):
        """确认导入时可选择转账交易类别（下拉框只显示转账分类，与添加交易页一致）"""
        _create_fund_accounts(app, test_owner)
        _create_bank_account(app, test_owner)

        with app.app_context():
            cat = Category(
                category_name='基金购买',
                category_class='投资',
                category_subclass='基金',
                category_type=CategoryType.TRANSFER
            )
            db.session.add(cat)
            expense_cat = Category(
                category_name='基金费用',
                category_class='投资',
                category_subclass='费用',
                category_type=CategoryType.EXPENSE
            )
            db.session.add(expense_cat)
            db.session.commit()
            cat_id = cat.category_id

        resp = logged_in_client.post(
            '/import/fund-purchases/upload',
            data={'file': (io.BytesIO(FUND_CSV.encode('utf-8')), 'fund.csv')},
            content_type='multipart/form-data',
            follow_redirects=True
        )
        assert resp.status_code == 200
        assert '交易类别'.encode('utf-8') in resp.data
        # 转账分类显示（与添加交易页格式一致）；支出分类不显示
        assert '投资 › 基金 › 基金购买'.encode('utf-8') in resp.data
        assert '基金费用'.encode('utf-8') not in resp.data
        # 不再有伪造的"账户转账（默认）"选项
        assert '账户转账（默认）'.encode('utf-8') not in resp.data

        resp = logged_in_client.post('/import/fund-purchases/confirm', data={
            'fund_category': cat_id,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert '基金购买导入完成：成功 2'.encode('utf-8') in resp.data

        with app.app_context():
            txns = db.session.scalars(select(Transaction)).all()
            assert len(txns) == 4
            for t in txns:
                assert t.trans_category_id == cat_id
