from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from flask_login import UserMixin
from sqlalchemy import (Boolean, Date, DateTime, Enum as SAEnum, Float, ForeignKey,
                        Integer, String, UniqueConstraint)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship)

from app import db, login_manager


# ===============================================================
# 基类定义
# ===============================================================

class Base(DeclarativeBase):
    pass


# ===============================================================
# 枚举定义
# ===============================================================

class AccountType(str, Enum):
    CASH = 'CASH'
    SAVING = 'SAVING'
    TIME_DEPOSIT = 'TIME_DEPOSIT'
    CURRENCY_LINKED_DEPOSIT = 'CURRENCY_LINKED_DEPOSIT'
    FUND = 'FUND'
    INVESTMENT = 'INVESTMENT'
    CREDIT_CARD = 'CREDIT_CARD'
    MORTGAGE = 'MORTGAGE'
    MPF = 'MPF'

    @property
    def is_liability(self):
        return self in (AccountType.CREDIT_CARD, AccountType.MORTGAGE)


class CategoryType(str, Enum):
    INCOME = 'I'
    EXPENSE = 'E'
    TRANSFER = 'T'
    SPECIAL = 'S'


class UserRole(str, Enum):
    ADULT = 'ADULT'
    CHILD = 'CHILD'


class DepositStatus(str, Enum):
    IN_PROGRESS = 'IN_PROGRESS'
    MATURED = 'MATURED'


class TransactionStatus(str, Enum):
    UNVERIFIED = 'UNVERIFIED'      # 未核对
    VERIFIED = 'VERIFIED'          # 已核对
    FLAGGED = 'FLAGGED'            # 标记（有疑问）


# ===============================================================
# 家庭表 - Family
# ===============================================================

class Family(Base):
    __tablename__ = 'family'

    family_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    members: Mapped[list[User]] = relationship('User', back_populates='family', lazy='dynamic')
    owners: Mapped[list[Owner]] = relationship('Owner', back_populates='family', lazy='dynamic')

    def __repr__(self):
        return f'<Family {self.family_name}>'


# ===============================================================
# 用户表 - User (扩展自MVP版本)
# ===============================================================

class User(UserMixin, Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.ADULT, nullable=False)
    family_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('family.family_id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    family: Mapped[Family | None] = relationship(back_populates='members')
    owner: Mapped[Owner | None] = relationship(back_populates='user', uselist=False)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def is_adult(self):
        return self.role == UserRole.ADULT

    def can_view_family_data(self):
        """成人可查看家庭所有数据"""
        return self.role == UserRole.ADULT

    def __repr__(self):
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ===============================================================
# 所有者表 - Owner (交易主体)
# ===============================================================

class Owner(Base):
    __tablename__ = 'owner'

    owner_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_id: Mapped[int] = mapped_column(Integer, ForeignKey('family.family_id'), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('user.id'), nullable=True)

    # 关系
    family: Mapped[Family] = relationship(back_populates='owners')
    user: Mapped[User | None] = relationship(back_populates='owner', uselist=False)
    accounts: Mapped[list[Account]] = relationship('Account', back_populates='owner', lazy='dynamic')
    transactions: Mapped[list[Transaction]] = relationship(
        'Transaction', back_populates='owner_rel', lazy='dynamic',
        foreign_keys='Transaction.trans_owner_id'
    )

    def __repr__(self):
        return f'<Owner {self.owner_name}>'


# ===============================================================
# 账户表 - Account
# ===============================================================

class Account(Base):
    __tablename__ = 'account'

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_other_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(SAEnum(AccountType), nullable=False)
    account_create_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    account_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    account_custodian: Mapped[str] = mapped_column(String(100), nullable=False)
    account_currency_name: Mapped[str] = mapped_column(String(3), default='HKD', nullable=False)
    account_owner_id: Mapped[int] = mapped_column(Integer, ForeignKey('owner.owner_id'), nullable=False)
    # 是否有单位概念（如基金份额）；基金账户默认为 True
    account_has_unit_ind: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 证券/基金 ISIN 代码（12 位，如 HK0000064689）；基金等有价证券账户使用
    account_isin: Mapped[str | None] = mapped_column(String(12), nullable=True)

    @property
    def has_unit_concept(self):
        """账户是否按单位/单价记录交易"""
        return self.account_has_unit_ind

    # 关系
    owner: Mapped[Owner] = relationship(back_populates='accounts')
    transactions: Mapped[list[Transaction]] = relationship(
        'Transaction', back_populates='account_rel', lazy='dynamic',
        foreign_keys='Transaction.trans_account_id'
    )
    balances: Mapped[list[AccountBalance]] = relationship('AccountBalance', back_populates='account', lazy='dynamic')
    bluecoins_mappings: Mapped[list[BluecoinsAccountMapping]] = relationship(
        'BluecoinsAccountMapping', back_populates='account', lazy='dynamic'
    )

    __table_args__ = (
        UniqueConstraint(
            'account_name', 'account_type', 'account_custodian',
            'account_currency_name', 'account_owner_id',
            name='uq_account_unique'
        ),
    )

    def __repr__(self):
        return f'<Account {self.account_name} ({self.account_type.value})>'


# ===============================================================
# 分类表 - Category
# ===============================================================

class Category(Base):
    __tablename__ = 'category'

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_other_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_class: Mapped[str] = mapped_column(String(100), nullable=False)
    category_subclass: Mapped[str] = mapped_column(String(100), nullable=False)
    category_type: Mapped[CategoryType] = mapped_column(SAEnum(CategoryType), nullable=False)

    # 关系
    transactions: Mapped[list[Transaction]] = relationship('Transaction', back_populates='category_rel', lazy='dynamic')
    bluecoins_mappings: Mapped[list[BluecoinsCategoryMapping]] = relationship(
        'BluecoinsCategoryMapping', back_populates='category', lazy='dynamic'
    )

    __table_args__ = (
        UniqueConstraint(
            'category_name', 'category_class', 'category_subclass', 'category_type',
            name='uq_category_unique'
        ),
    )

    def __repr__(self):
        return f'<Category {self.category_name} ({self.category_type.value})>'


# ===============================================================
# 交易表 - Transaction (核心)
# ===============================================================

class Transaction(Base):
    __tablename__ = 'transaction'

    trans_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trans_datetime: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    trans_desc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trans_amount: Mapped[float] = mapped_column(Float, nullable=False)
    trans_currency_name: Mapped[str] = mapped_column(String(3), default='HKD', nullable=False)
    trans_account_id: Mapped[int] = mapped_column(Integer, ForeignKey('account.account_id'), nullable=False)
    trans_category_id: Mapped[int] = mapped_column(Integer, ForeignKey('category.category_id'), nullable=False)
    trans_owner_id: Mapped[int] = mapped_column(Integer, ForeignKey('owner.owner_id'), nullable=False)
    trans_status: Mapped[TransactionStatus] = mapped_column(SAEnum(TransactionStatus), default=TransactionStatus.UNVERIFIED, nullable=False)

    # 转账配对
    trans_counter_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('transaction.trans_id'), nullable=True)

    # 外汇交易：trans_fx_currency_name=外汇货币，trans_fx_rate=汇率（1 HKD = X trans_fx_currency_name），trans_fx_amount=外汇金额
    trans_fx_currency_name: Mapped[str | None] = mapped_column(String(3), nullable=True)
    trans_fx_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    trans_fx_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    # trans_fx_currency_name 为外汇货币时，trans_is_rhs_currency_ind 必填：trans_currency_name 是否为汇率对的 RHS（如 USD/HKD 的 HKD）
    trans_is_rhs_currency_ind: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # 投资单位（基金等）：trans_unit=份额，trans_unit_price=单价，trans_unit_name=单位名称
    trans_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    trans_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    trans_unit_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 存款关联 (MVP阶段预留)
    trans_deposit_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('time_deposit.deposit_id'), nullable=True)

    # 关系
    account_rel: Mapped[Account] = relationship(back_populates='transactions')
    category_rel: Mapped[Category] = relationship(back_populates='transactions')
    owner_rel: Mapped[Owner] = relationship(back_populates='transactions')
    deposit: Mapped[TimeDeposit | None] = relationship(back_populates='transactions',
                                                       foreign_keys=[trans_deposit_id])

    counter_transaction: Mapped[Transaction | None] = relationship(
        'Transaction',
        remote_side=[trans_id],
        foreign_keys=[trans_counter_id],
        back_populates='paired_transaction',
        uselist=False
    )
    paired_transaction: Mapped[Transaction | None] = relationship(
        'Transaction',
        back_populates='counter_transaction',
        uselist=False
    )

    def is_transfer(self):
        """判断是否为转账交易"""
        return self.trans_counter_id is not None

    @property
    def is_fx(self):
        """判断是否为外汇交易"""
        return self.trans_fx_currency_name is not None

    def is_income(self):
        """判断是否为收入"""
        return self.trans_amount > 0 and not self.is_transfer()

    def is_expense(self):
        """判断是否为支出"""
        return self.trans_amount < 0 and not self.is_transfer()

    def __repr__(self):
        return f'<Transaction {self.trans_id}: {self.trans_amount} {self.trans_currency_name}>'


# ===============================================================
# 账户余额表 - AccountBalance (EOD Balance)
# ===============================================================

class AccountBalance(Base):
    __tablename__ = 'account_balance'

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_dt: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey('account.account_id'), nullable=False)
    account_balance: Mapped[float] = mapped_column(Float, nullable=False)

    # 外汇账户扩展 (预留)
    deposit_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    account_fx_currency_name: Mapped[str | None] = mapped_column(String(3), nullable=True)
    account_fx_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    account_unit_cost_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 关系
    account: Mapped[Account] = relationship(back_populates='balances')

    def __repr__(self):
        return f'<Balance {self.account_id} as of {self.as_of_dt}: {self.account_balance}>'


# ===============================================================
# 定期存款表 - TimeDeposit (MVP阶段预留)
# ===============================================================

class TimeDeposit(Base):
    __tablename__ = 'time_deposit'

    deposit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[DepositStatus] = mapped_column(SAEnum(DepositStatus), default=DepositStatus.IN_PROGRESS, nullable=False)
    deposit_currency_name: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    interest_rate: Mapped[float] = mapped_column(Float, nullable=False)
    subscription_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    matured_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # CLD扩展 (预留)
    matured_currency_name: Mapped[str | None] = mapped_column(String(3), nullable=True)
    linked_currency_name: Mapped[str | None] = mapped_column(String(3), nullable=True)
    linked_currency_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    strike_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)
    fx_value_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 关系
    transactions: Mapped[list[Transaction]] = relationship('Transaction', back_populates='deposit', lazy='dynamic')

    def __repr__(self):
        return f'<TimeDeposit {self.deposit_id}: {self.amount} {self.deposit_currency_name}>'


# ===============================================================
# 货币转换表 - CurrencyConversion (预留)
# ===============================================================

class CurrencyConversion(Base):
    __tablename__ = 'currency_conversion'

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    currency_name_lhs: Mapped[str] = mapped_column(String(3), nullable=False)
    currency_name_rhs: Mapped[str] = mapped_column(String(3), nullable=False, default='HKD')
    currency_conversion_rate: Mapped[float] = mapped_column(Float, nullable=False)
    currency_conversion_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('currency_name_lhs', 'currency_name_rhs', 'currency_conversion_date',
                         name='uq_currency_rate_date'),
        {'extend_existing': True},
    )

    def __repr__(self):
        return f'<FX {self.currency_name_lhs}/{self.currency_name_rhs} = {self.currency_conversion_rate}>'


# ===============================================================
# Bluecoins 映射表
# ===============================================================

class BluecoinsAccountMapping(Base):
    """Bluecoins 账户名 → 系统 Account 映射"""
    __tablename__ = 'bluecoins_account_mapping'

    mapping_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bluecoins_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey('account.account_id'), nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    account: Mapped[Account] = relationship(back_populates='bluecoins_mappings')

    def __repr__(self):
        return f'<BC AccountMap {self.bluecoins_name} → Account {self.account_id}>'


class BluecoinsCategoryMapping(Base):
    """Bluecoins 五元组 → 系统 Category 映射（全局，不区分 owner）"""
    __tablename__ = 'bluecoins_category_mapping'

    mapping_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bluecoins_year: Mapped[str] = mapped_column(String(10), nullable=False)
    bluecoins_type: Mapped[str] = mapped_column(String(20), nullable=False)
    bluecoins_group: Mapped[str] = mapped_column(String(200), nullable=False)
    bluecoins_category: Mapped[str] = mapped_column(String(200), nullable=False)
    bluecoins_title: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey('category.category_id'), nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    category: Mapped[Category] = relationship(back_populates='bluecoins_mappings')

    # 五元组联合唯一索引（全局）
    __table_args__ = (
        UniqueConstraint(
            'bluecoins_year', 'bluecoins_type', 'bluecoins_group',
            'bluecoins_category', 'bluecoins_title',
            name='uq_bc_category_mapping'
        ),
    )

    def __repr__(self):
        return f'<BC CategoryMap {self.bluecoins_group}/{self.bluecoins_category}/{self.bluecoins_title} → Category {self.category_id}>'