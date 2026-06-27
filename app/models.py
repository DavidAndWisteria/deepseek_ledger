from datetime import datetime, timezone
from enum import Enum
from flask_login import UserMixin
from app import db, login_manager


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

class Family(db.Model):
    __tablename__ = 'family'
    
    family_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    family_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 关系
    members = db.relationship('User', backref='family', lazy='dynamic')
    owners = db.relationship('Owner', backref='family', lazy='dynamic')
    
    def __repr__(self):
        return f'<Family {self.family_name}>'


# ===============================================================
# 用户表 - User (扩展自MVP版本)
# ===============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.Enum(UserRole), default=UserRole.ADULT, nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('family.family_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 关系
    owner = db.relationship('Owner', backref='user', uselist=False, lazy=True)
    
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

class Owner(db.Model):
    __tablename__ = 'owner'
    
    owner_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_name = db.Column(db.String(100), nullable=False)
    family_id = db.Column(db.Integer, db.ForeignKey('family.family_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # 关系
    accounts = db.relationship('Account', backref='owner', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='owner_rel', lazy='dynamic',
                                   foreign_keys='Transaction.trans_owner_id')
    
    def __repr__(self):
        return f'<Owner {self.owner_name}>'


# ===============================================================
# 账户表 - Account
# ===============================================================

class Account(db.Model):
    __tablename__ = 'account'
    
    account_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    account_name = db.Column(db.String(100), nullable=False)
    account_other_name = db.Column(db.String(100), nullable=True)
    account_type = db.Column(db.Enum(AccountType), nullable=False)
    account_create_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    account_close_date = db.Column(db.Date, nullable=True)
    account_custodian = db.Column(db.String(100), nullable=False)
    account_currency_name = db.Column(db.String(3), default='HKD', nullable=False)
    account_owner_id = db.Column(db.Integer, db.ForeignKey('owner.owner_id'), nullable=False)
    
    # 关系
    transactions = db.relationship('Transaction', backref='account_rel', lazy='dynamic',
                                   foreign_keys='Transaction.trans_account_id')
    balances = db.relationship('AccountBalance', backref='account', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint(
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

class Category(db.Model):
    __tablename__ = 'category'
    
    category_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_name = db.Column(db.String(100), nullable=False)
    category_other_name = db.Column(db.String(100), nullable=True)
    category_class = db.Column(db.String(100), nullable=False)
    category_subclass = db.Column(db.String(100), nullable=False)
    category_type = db.Column(db.Enum(CategoryType), nullable=False)
    
    # 关系
    transactions = db.relationship('Transaction', backref='category_rel', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint(
            'category_name', 'category_class', 'category_subclass', 'category_type',
            name='uq_category_unique'
        ),
    )

    def __repr__(self):
        return f'<Category {self.category_name} ({self.category_type.value})>'


# ===============================================================
# 交易表 - Transaction (核心)
# ===============================================================

class Transaction(db.Model):
    __tablename__ = 'transaction'
    
    trans_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    trans_datetime = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    trans_desc = db.Column(db.String(500), nullable=True)
    trans_amount = db.Column(db.Float, nullable=False)
    trans_currency_name = db.Column(db.String(3), default='HKD', nullable=False)
    trans_account_id = db.Column(db.Integer, db.ForeignKey('account.account_id'), nullable=False)
    trans_category_id = db.Column(db.Integer, db.ForeignKey('category.category_id'), nullable=False)
    trans_owner_id = db.Column(db.Integer, db.ForeignKey('owner.owner_id'), nullable=False)
    trans_status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.UNVERIFIED, nullable=False)
    
    # 转账配对
    trans_counter_id = db.Column(db.Integer, db.ForeignKey('transaction.trans_id'), nullable=True)
    
    # 外汇相关 (MVP阶段预留)
    trans_fx_currency_name = db.Column(db.String(3), nullable=True)
    trans_fx_amount = db.Column(db.Float, nullable=True)
    trans_fx_rate = db.Column(db.Float, nullable=True)
    trans_is_rhs_currency_ind = db.Column(db.Boolean, nullable=True)
    
    # 存款关联 (MVP阶段预留)
    trans_deposit_id = db.Column(db.Integer, db.ForeignKey('time_deposit.deposit_id'), nullable=True)
    
    # 关系
    counter_transaction = db.relationship('Transaction', remote_side=[trans_id], 
                                          backref=db.backref('paired_transaction', uselist=False))
    
    def is_transfer(self):
        """判断是否为转账交易"""
        return self.trans_counter_id is not None
    
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

class AccountBalance(db.Model):
    __tablename__ = 'account_balance'
    
    record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    as_of_dt = db.Column(db.Date, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.account_id'), nullable=False)
    account_balance = db.Column(db.Float, nullable=False)
    
    # 外汇账户扩展 (预留)
    deposit_unit = db.Column(db.Float, nullable=True)
    account_fx_currency_name = db.Column(db.String(3), nullable=True)
    account_fx_amount = db.Column(db.Float, nullable=True)
    account_unit_cost_rate = db.Column(db.Float, nullable=True)
    
    def __repr__(self):
        return f'<Balance {self.account_id} as of {self.as_of_dt}: {self.account_balance}>'


# ===============================================================
# 定期存款表 - TimeDeposit (MVP阶段预留)
# ===============================================================

class TimeDeposit(db.Model):
    __tablename__ = 'time_deposit'
    
    deposit_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    status = db.Column(db.Enum(DepositStatus), default=DepositStatus.IN_PROGRESS, nullable=False)
    deposit_currency_name = db.Column(db.String(3), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)
    subscription_date = db.Column(db.Date, nullable=False)
    maturity_date = db.Column(db.Date, nullable=False)
    realized_pnl = db.Column(db.Float, nullable=True)
    matured_amount = db.Column(db.Float, nullable=True)
    
    # CLD扩展 (预留)
    matured_currency_name = db.Column(db.String(3), nullable=True)
    linked_currency_name = db.Column(db.String(3), nullable=True)
    linked_currency_amount = db.Column(db.Float, nullable=True)
    strike_rate = db.Column(db.Float, nullable=True)
    unit = db.Column(db.Float, nullable=True)
    cost_per_unit = db.Column(db.Float, nullable=True)
    fx_value_per_unit = db.Column(db.Float, nullable=True)
    
    # 关系
    transactions = db.relationship('Transaction', backref='deposit', lazy='dynamic')
    
    def __repr__(self):
        return f'<TimeDeposit {self.deposit_id}: {self.amount} {self.deposit_currency_name}>'


# ===============================================================
# 货币转换表 - CurrencyConversion (预留)
# ===============================================================

class CurrencyConversion(db.Model):
    __tablename__ = 'currency_conversion'

    record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    currency_name_lhs = db.Column(db.String(3), nullable=False)
    currency_name_rhs = db.Column(db.String(3), nullable=False, default='HKD')
    currency_conversion_rate = db.Column(db.Float, nullable=False)
    currency_conversion_date = db.Column(db.Date, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('currency_name_lhs', 'currency_name_rhs', 'currency_conversion_date',
                            name='uq_currency_rate_date'),
        {'extend_existing': True},
    )

    def __repr__(self):
        return f'<FX {self.currency_name_lhs}/{self.currency_name_rhs} = {self.currency_conversion_rate}>'
    

# ===============================================================
# Bluecoins 映射表
# ===============================================================

class BluecoinsAccountMapping(db.Model):
    """Bluecoins 账户名 → 系统 Account 映射"""
    __tablename__ = 'bluecoins_account_mapping'
    
    mapping_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bluecoins_name = db.Column(db.String(200), nullable=False, index=True)  # Bluecoins 原始账户名
    account_id = db.Column(db.Integer, db.ForeignKey('account.account_id'), nullable=False)
    is_manual = db.Column(db.Boolean, default=False)  # 是否为手动映射
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    account = db.relationship('Account', backref='bluecoins_mappings')
    
    def __repr__(self):
        return f'<BC AccountMap {self.bluecoins_name} → Account {self.account_id}>'


class BluecoinsCategoryMapping(db.Model):
    """Bluecoins 五元组 → 系统 Category 映射（全局，不区分 owner）"""
    __tablename__ = 'bluecoins_category_mapping'
    
    mapping_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bluecoins_year = db.Column(db.String(10), nullable=False)
    bluecoins_type = db.Column(db.String(20), nullable=False)       # Bluecoins 类型（收入/支出/转账）
    bluecoins_group = db.Column(db.String(200), nullable=False)     # 类别分组名称
    bluecoins_category = db.Column(db.String(200), nullable=False)  # 类别
    bluecoins_title = db.Column(db.String(200), nullable=False)     # 标题
    category_id = db.Column(db.Integer, db.ForeignKey('category.category_id'), nullable=False)
    is_manual = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 关系
    category = db.relationship('Category', backref='bluecoins_mappings')
    
    # 五元组联合唯一索引（全局）
    __table_args__ = (
        db.UniqueConstraint(
            'bluecoins_year', 'bluecoins_type', 'bluecoins_group',
            'bluecoins_category', 'bluecoins_title',
            name='uq_bc_category_mapping'
        ),
    )
    
    def __repr__(self):
        return f'<BC CategoryMap {self.bluecoins_group}/{self.bluecoins_category}/{self.bluecoins_title} → Category {self.category_id}>'


