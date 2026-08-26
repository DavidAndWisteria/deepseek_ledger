# 数据库设计文档

---

## 概述

本项目使用 SQLite 作为数据库，通过 SQLAlchemy ORM 进行管理。启动应用时自动检查表结构，缺失列时自动迁移并保留数据。

---

## 实体关系图 (ER Diagram)

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Family   │────→│   User   │────→│  Owner   │
└──────────┘     └──────────┘     └──────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ↓                  ↓                  ↓
              ┌──────────┐     ┌──────────┐     ┌──────────────┐
              │  Account │     │Transaction│     │AccountBalance│
              └──────────┘     └──────────┘     └──────────────┘
                    │               │
                    │          ┌────┴────┐
                    │          ↓         ↓
                    │   ┌──────────┐ ┌──────────────┐
                    │   │ Category │ │TimeDeposit   │
                    │   └──────────┘ └──────────────┘
                    │
              ┌─────┴──────────┬──────────────────┐
              │CurrencyConversion│BluecoinsMappings│
              └────────────────┘──────────────────┘
```

---

## 表结构详情

### 1. Family（家庭表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| family_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 家庭唯一标识 |
| family_name | VARCHAR(100) | NOT NULL | 家庭名称 |
| created_at | DATETIME | DEFAULT UTC_TIMESTAMP | 创建时间 |

**关系**：
- 一对多 → User（一个家庭有多个用户）
- 一对多 → Owner（一个家庭有多个所有者）

---

### 2. User（用户表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY | 用户唯一标识 |
| username | VARCHAR(80) | UNIQUE, NOT NULL, INDEX | 登录用户名 |
| password_hash | VARCHAR(120) | NOT NULL | bcrypt 密码哈希 |
| role | ENUM | NOT NULL, DEFAULT 'ADULT' | 角色：ADULT/CHILD |
| family_id | INTEGER | FOREIGN KEY → family.family_id | 所属家庭 |
| created_at | DATETIME | DEFAULT UTC_TIMESTAMP | 创建时间 |

**角色说明**：
- `ADULT`：可查看家庭所有数据，管理成员、账户、分类
- `CHILD`：仅可查看自己的数据

**关系**：
- 多对一 → Family
- 一对一 → Owner

---

### 3. Owner（所有者表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| owner_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 所有者唯一标识 |
| owner_name | VARCHAR(100) | NOT NULL | 所有者名称（称呼） |
| family_id | INTEGER | FOREIGN KEY → family.family_id, NOT NULL | 所属家庭 |
| user_id | INTEGER | FOREIGN KEY → user.id, NULLABLE | 关联登录用户 |

**关系**：
- 多对一 → Family
- 多对一 → User（可选，未关联用户则无法登录）
- 一对多 → Account
- 一对多 → Transaction

---

### 4. Account（账户表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| account_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 账户唯一标识 |
| account_name | VARCHAR(100) | NOT NULL | 账户名称 |
| account_other_name | VARCHAR(100) | NULLABLE | 账户别名 |
| account_type | ENUM | NOT NULL | 账户类型 |
| account_create_date | DATE | DEFAULT TODAY | 创建日期 |
| account_close_date | DATE | NULLABLE | 关闭日期 |
| account_custodian | VARCHAR(100) | NOT NULL | 机构/钱包 |
| account_currency_name | CHAR(3) | DEFAULT 'HKD' | 货币代码 |
| account_owner_id | INTEGER | FOREIGN KEY → owner.owner_id, NOT NULL | 账户拥有者 |
| account_has_unit_ind | BOOLEAN | DEFAULT FALSE | 是否有单位概念（按单位/单价记账，如基金份额）；基金账户默认为 True |
| account_isin | VARCHAR(12) | NULLABLE | 证券/基金 ISIN 代码（12 位，如 HK0000064689）；基金等有价证券账户使用 |

**账户类型枚举 (AccountType)**：

| 值 | 说明 |
|------|------|
| CASH | 现金 |
| SAVING | 储蓄账户 |
| TIME_DEPOSIT | 定期存款 |
| CURRENCY_LINKED_DEPOSIT | 货币挂钩存款 |
| FUND | 基金 |
| INVESTMENT | 投资账户 |
| CREDIT_CARD | 信用卡 |
| MORTGAGE | 按揭贷款 |
| MPF | 强积金 |

**显示排序**：类型 → 机构 → 拥有者 → 名称

---

### 5. Category（分类表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| category_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 分类唯一标识 |
| category_name | VARCHAR(100) | NOT NULL | 分类名称 |
| category_other_name | VARCHAR(100) | NULLABLE | 分类别名 |
| category_class | VARCHAR(100) | NOT NULL | 大类 |
| category_subclass | VARCHAR(100) | NOT NULL | 子类 |
| category_type | ENUM | NOT NULL | 分类类型 |

**分类类型枚举 (CategoryType)**：

| 值 | 说明 | 使用场景 |
|------|------|---------|
| I | 收入 | 工资、兼职、投资收益等 |
| E | 支出 | 餐饮、交通、购物等 |
| T | 转账 | 账户间转账 |
| S | 特殊 | 账户初始化等特殊操作 |

**显示排序**：大类 → 子类 → 名称

---

### 6. Transaction（交易表）⭐ 核心表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| trans_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 交易唯一标识 |
| trans_datetime | DATETIME | NOT NULL, DEFAULT UTC_NOW | 交易日期时间（精确到分钟） |
| trans_desc | VARCHAR(500) | NULLABLE | 交易描述/备注 |
| trans_amount | FLOAT | NOT NULL | 交易金额 |
| trans_currency_name | CHAR(3) | DEFAULT 'HKD' | 货币代码 |
| trans_account_id | INTEGER | FOREIGN KEY → account.account_id, NOT NULL | 交易账户 |
| trans_category_id | INTEGER | FOREIGN KEY → category.category_id, NOT NULL | 交易分类 |
| trans_owner_id | INTEGER | FOREIGN KEY → owner.owner_id, NOT NULL | 交易所有者 |
| trans_counter_id | INTEGER | FOREIGN KEY → transaction.trans_id, NULLABLE | 配对交易ID（转账用） |
| trans_status | ENUM | NOT NULL, DEFAULT 'UNVERIFIED' | 交易状态 |
| trans_fx_currency_name | CHAR(3) | NULLABLE | 外汇货币代码（如 USD），非空即为外汇交易 |
| trans_fx_rate | FLOAT | NULLABLE | 外汇汇率（1 HKD = X trans_fx_currency_name） |
| trans_fx_amount | FLOAT | NULLABLE | 外汇金额（带符号） |
| trans_is_rhs_currency_ind | BOOLEAN | NULLABLE | 外汇交易时必填：trans_currency_name 是否为汇率对 RHS（如 USD/HKD 的 HKD） |
| trans_unit | FLOAT | NULLABLE | 投资单位数（如基金份额，仅单位概念账户） |
| trans_unit_price | FLOAT | NULLABLE | 投资单位单价（账户默认货币计） |
| trans_unit_name | VARCHAR(100) | NULLABLE | 投资单位名称（预留） |
| trans_deposit_id | INTEGER | FOREIGN KEY → time_deposit.deposit_id, NULLABLE | 关联存款（预留） |

**交易状态枚举 (TransactionStatus)**：

| 值 | 说明 | 图标 |
|------|------|------|
| UNVERIFIED | 未核对（默认） | ⚠ |
| VERIFIED | 已核对 | ✓ |
| FLAGGED | 有疑问 | ⚑ |
| RECONCILED | 已对账 | ✓✓ |

**交易逻辑**：

| 类型 | trans_amount | trans_counter_id | 说明 |
|------|-------------|-----------------|------|
| 收入 | 正数 | NULL | 单条记录 |
| 支出 | 负数 | NULL | 单条记录 |
| 转账(出) | 负数 | 配对 trans_id | 与转入记录配对 |
| 转账(入) | 正数 | 配对 trans_id | 与转出记录配对 |

**状态流转**：

```
UNVERIFIED ──核对──→ VERIFIED
    ↑                   │
    └──取消核对─────────┘
    │
    └──标记──→ FLAGGED
                  │
                  └──取消标记──→ UNVERIFIED
```

---

### 7. AccountBalance（账户余额表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| record_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 记录唯一标识 |
| as_of_dt | DATE | NOT NULL | 截至日期 |
| account_id | INTEGER | FOREIGN KEY → account.account_id, NOT NULL | 关联账户 |
| account_balance | FLOAT | NOT NULL | 账户余额 |
| deposit_unit | FLOAT | NULLABLE | 存款单位（预留） |
| account_fx_currency_name | CHAR(3) | NULLABLE | 外汇货币（预留） |
| account_fx_amount | FLOAT | NULLABLE | 外汇金额（预留） |
| account_unit_cost_rate | FLOAT | NULLABLE | 单位成本汇率（预留） |

**说明**：用于记录账户日终余额（EOD Balance），当前版本暂未在前端实现。

---

### 8. TimeDeposit（定期存款表）⏳ 预留

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| deposit_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 存款唯一标识 |
| status | ENUM | DEFAULT 'IN_PROGRESS' | 状态：IN_PROGRESS/MATURED |
| deposit_currency_name | CHAR(3) | NOT NULL | 存款货币 |
| amount | FLOAT | NOT NULL | 存款金额 |
| interest_rate | FLOAT | NOT NULL | 利率(%) |
| subscription_date | DATE | NOT NULL | 认购日期 |
| maturity_date | DATE | NOT NULL | 到期日期 |
| realized_pnl | FLOAT | NULLABLE | 实现盈亏 |
| matured_amount | FLOAT | NULLABLE | 到期金额 |
| matured_currency_name | CHAR(3) | NULLABLE | 到期货币（CLD用） |
| linked_currency_name | CHAR(3) | NULLABLE | 挂钩货币（CLD用） |
| linked_currency_amount | FLOAT | NULLABLE | 挂钩货币金额（CLD用） |
| strike_rate | FLOAT | NULLABLE | 行使汇率（CLD用） |
| unit | FLOAT | NULLABLE | 单位（CLD用） |
| cost_per_unit | FLOAT | NULLABLE | 单位成本（CLD用） |
| fx_value_per_unit | FLOAT | NULLABLE | 单位外汇价值（CLD用） |

**说明**：当前版本预留，后续版本实现定期存款和货币挂钩存款管理。

---

### 9. CurrencyConversion（货币转换表）⏳ 预留

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| record_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 记录唯一标识 |
| currency_name_lhs | CHAR(3) | NOT NULL | 左侧货币 |
| currency_name_rhs | CHAR(3) | NOT NULL | 右侧货币 |
| currency_conversion_rate | FLOAT | NOT NULL | 转换汇率 (LHS/RHS) |
| currency_conversion_date | DATE | NOT NULL | 汇率日期 |

**说明**：当前版本预留，后续版本实现多货币转换功能。基础货币为 HKD。

---

### 10. BluecoinsAccountMapping（Bluecoins 账户映射表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| bluecoins_name | VARCHAR(200) | PRIMARY KEY | Bluecoins 原始账户名 |
| account_id | INTEGER | FOREIGN KEY → account.account_id, NOT NULL | 映射到的系统账户 |
| is_manual | BOOLEAN | DEFAULT FALSE | 是否为手动映射 |
| created_at | DATETIME | DEFAULT UTC_TIMESTAMP | 创建时间 |

**说明**: 将 Bluecoins 导出的账户名称映射到系统 Account。导入账户 CSV 或手动映射时自动创建。

---

### 11. BluecoinsCategoryMapping（Bluecoins 分类映射表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| bluecoins_year | VARCHAR(4) | PRIMARY KEY (联合) | Bluecoins 年份 |
| bluecoins_type | VARCHAR(10) | PRIMARY KEY (联合) | Bluecoins 类型：收入/支出/转账 |
| bluecoins_group | VARCHAR(100) | PRIMARY KEY (联合) | Bluecoins 类别分组名称 |
| bluecoins_category | VARCHAR(100) | PRIMARY KEY (联合) | Bluecoins 类别 |
| bluecoins_title | VARCHAR(200) | PRIMARY KEY (联合) | Bluecoins 标题 |
| category_id | INTEGER | FOREIGN KEY → category.category_id, NOT NULL | 映射到的系统分类 |
| is_manual | BOOLEAN | DEFAULT FALSE | 是否为手动映射 |
| created_at | DATETIME | DEFAULT UTC_TIMESTAMP | 创建时间 |

**说明**: 五元组联合主键 `(year, type, group, category, title)` 唯一标识 Bluecoins 分类，映射到系统 Category。手动映射（`is_manual=True`）会自动覆盖同 `(type, group, category, title)` 的自动映射。

---

## 数据权限模型

```
Family (家庭)
  ├── Owner A (成人) → User A
  │   ├── 可见：家庭所有交易
  │   ├── 可管理：所有成员、账户、分类
  │   └── 可操作：重置其他成员密码
  │
  ├── Owner B (成人) → User B
  │   ├── 可见：家庭所有交易
  │   └── 可管理：所有成员、账户、分类
  │
  └── Owner C (小孩) → User C
      ├── 可见：仅自己的交易
      └── 不可管理成员
```

---

## 索引策略

| 表 | 索引 | 类型 |
|------|------|------|
| user | username | UNIQUE INDEX |
| user | family_id | INDEX |
| owner | family_id | INDEX |
| account | account_owner_id | INDEX |
| transaction | trans_owner_id | INDEX |
| transaction | trans_account_id | INDEX |
| transaction | trans_category_id | INDEX |
| transaction | trans_datetime | INDEX（查询排序） |

---

## 自动迁移机制

启动应用时自动执行：

1. 检查数据库中是否存在所有模型定义的表
2. 对于存在的表，检查列是否与模型定义一致
3. 缺失的列 → 备份数据 → 删除旧表 → 创建新表 → 恢复数据
4. 新增的表 → 直接创建

**注意**：不检测列类型变更和已删除的列。

---

## 开发数据库隔离

- **开发环境**: `instance/ledger.db`
- **测试环境**: 临时文件（每次测试自动创建和删除）
- **隔离机制**: `create_app(test_config={...})` 在 `db.init_app()` 之前注入临时 DB URI，确保 SQLAlchemy engine 绑定到临时数据库而非开发数据库
- **pytest 启动时**: 自动备份 `ledger.db` → `ledger.db.backup`
- **pytest 结束时**: 自动恢复 `ledger.db.backup` → `ledger.db`

---

**最后更新**：2026年6月10日