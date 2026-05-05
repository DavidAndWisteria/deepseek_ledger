# API 接口文档

---

## 基础信息

- **基础URL**: `http://127.0.0.1:5000`
- **内容类型**: `application/x-www-form-urlencoded` (表单提交)
- **认证方式**: Session Cookie (Flask-Login)
- **CSRF保护**: 所有 POST 请求需携带 `csrf_token`

---

## 认证接口

### 登录页面

```http
GET /login
```

**响应**: HTML 登录页面

---

### 登录请求

```http
POST /login
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码 |
| csrf_token | string | 是 | CSRF 令牌 |

**成功响应**: 重定向到仪表盘 `/`

**失败响应**: 重定向回 `/login`，Flash 消息提示错误

---

### 注册页面

```http
GET /register
```

**响应**: HTML 注册页面

---

### 注册请求

```http
POST /register
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名（3-80字符，字母数字下划线） |
| password | string | 是 | 密码（至少8字符） |
| family_name | string | 是 | 家庭名称 |
| owner_name | string | 是 | 成员称呼 |
| role | string | 是 | 角色：ADULT/CHILD |
| csrf_token | string | 是 | CSRF 令牌 |

**成功响应**: 自动登录并重定向到仪表盘

**失败响应**: 重定向回 `/register`，Flash 消息提示验证错误

---

### 退出登录

```http
GET /logout
```

**说明**: 需登录状态

**响应**: 重定向到登录页面

---

## 交易接口

### 仪表盘

```http
GET /
```

**说明**: 需登录状态。显示交易列表、统计数据和筛选功能。

**查询参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|------|------|
| start_date | string | 否 | 当月1日 | 开始日期 (YYYY-MM-DD) |
| end_date | string | 否 | 当月最后一日 | 结束日期 (YYYY-MM-DD) |
| status | string | 否 | 空(全部) | 交易状态筛选 |
| category_id | int | 否 | 空(全部) | 分类筛选 |
| account_id | int | 否 | 空(全部) | 账户筛选 |
| tab | string | 否 | add-tab | 当前标签页 (add-tab/list-tab) |

**status 可选值**:

| 值 | 说明 |
|------|------|
| UNVERIFIED | 未核对 |
| VERIFIED | 已核对 |
| FLAGGED | 有疑问 |
| RECONCILED | 已对账 |

**响应数据**:

| 字段 | 类型 | 说明 |
|------|------|------|
| transactions | list | 交易列表 |
| total_income | float | 总收入 |
| total_expense | float | 总支出 |
| total_transfer | float | 转账总额 |
| balance | float | 净收入 |
| unverified_count | int | 待核对数量 |
| accounts | list | 用户账户列表 |
| categories | list | 分类列表 |
| start_date | string | 筛选开始日期 |
| end_date | string | 筛选结束日期 |
| status_filter | string | 筛选状态 |
| category_filter | int/string | 筛选分类ID |
| account_filter | int/string | 筛选账户ID |
| active_tab | string | 当前标签页 |

---

### 添加交易

```http
POST /add
```

**说明**: 需登录状态。支持收入、支出、转账三种类型。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trans_type | string | 是 | 交易类型：income/expense/transfer |
| account_id | int | 是 | 账户ID |
| category_id | int | 是 | 分类ID |
| amount | float | 是 | 金额（正数，>0，≤99999999.99） |
| description | string | 否 | 备注（最大500字符） |
| trans_date | string | 是 | 日期 (YYYY-MM-DD) |
| trans_time | string | 否 | 时间 (HH:MM)，默认 00:00 |
| to_account_id | int | 转账必填 | 转入账户ID（仅转账类型） |
| csrf_token | string | 是 | CSRF 令牌 |

**交易类型说明**:

| 类型 | amount处理 | 说明 |
|------|-----------|------|
| income | 正数存储 | 收入记录 |
| expense | 负数存储 | 支出记录 |
| transfer | 负数(出)/正数(入) | 生成两条配对记录 |

**转账逻辑**:
1. 创建转出记录（trans_amount = -amount）
2. 创建转入记录（trans_amount = +amount）
3. 两条记录通过 `trans_counter_id` 互相关联
4. 默认状态为 `UNVERIFIED`

**成功响应**: 重定向到仪表盘（`?tab=list-tab`）

**失败响应**: Flash 消息提示验证错误

---

### 编辑交易

```http
POST /edit/<int:trans_id>
```

**说明**: 需登录状态。仅交易所有者可编辑。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_id | int | 是 | 账户ID |
| category_id | int | 是 | 分类ID |
| amount | float | 是 | 金额（正数） |
| description | string | 否 | 备注 |
| trans_date | string | 是 | 日期 (YYYY-MM-DD) |
| trans_time | string | 是 | 时间 (HH:MM) |
| csrf_token | string | 是 | CSRF 令牌 |

**说明**:
- 非转账交易：直接更新所有字段
- 转账交易：同时更新配对记录（金额符号相反）

**成功响应**: 重定向到仪表盘（`?tab=list-tab`）

---

### 删除交易

```http
POST /delete/<int:trans_id>
```

**说明**: 需登录状态。仅交易所有者可删除。转账交易会同时删除配对记录。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| csrf_token | string | 是 | CSRF 令牌 |

**成功响应**: 重定向到仪表盘（`?tab=list-tab`）

---

### 更新交易状态

```http
POST /status/<int:trans_id>/<status>
```

**说明**: 需登录状态。仅交易所有者可操作。

**路径参数**:

| 参数 | 说明 |
|------|------|
| trans_id | 交易ID |
| status | 目标状态：UNVERIFIED/VERIFIED/FLAGGED/RECONCILED |

**状态流转**:

```
UNVERIFIED ──→ VERIFIED（核对）
UNVERIFIED ──→ FLAGGED（标记有疑问）
VERIFIED  ──→ UNVERIFIED（取消核对）
FLAGGED   ──→ UNVERIFIED（取消标记）
```

**成功响应**: 重定向到仪表盘（`?tab=list-tab`）

---

### 批量核对

```http
POST /batch-verify
```

**说明**: 需登录状态。将选中的未核对交易批量标记为已核对。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trans_ids | list[int] | 是 | 交易ID列表（复选框值） |
| csrf_token | string | 是 | CSRF 令牌 |

**成功响应**: 重定向到仪表盘（`?tab=list-tab`），Flash 显示核对数量

---

## 账户接口

### 账户列表

```http
GET /accounts
```

**说明**: 需登录状态。成人可看家庭所有账户，小孩仅看自己。

**响应数据**:

| 字段 | 类型 | 说明 |
|------|------|------|
| accounts | list | 账户列表（按类型·机构·拥有者·名称排序） |
| account_types | list | 账户类型枚举 |
| members | list | 家庭成员列表 |
| current_owner | object | 当前用户 Owner |

---

### 添加账户

```http
POST /accounts/add
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| account_name | string | 是 | 账户名称 |
| account_type | string | 是 | 账户类型（枚举值） |
| account_custodian | string | 是 | 机构/钱包 |
| account_other_name | string | 否 | 账户别名 |
| currency | string | 否 | 货币代码（默认 HKD） |
| account_create_date | string | 否 | 创建日期 (YYYY-MM-DD) |
| account_close_date | string | 否 | 关闭日期 |
| account_owner_id | int | 否 | 拥有者ID（成人可为家庭成员创建） |
| csrf_token | string | 是 | CSRF 令牌 |

**货币代码**:

| 代码 | 说明 |
|------|------|
| HKD | 港币 |
| USD | 美元 |
| CNY | 人民币 |
| JPY | 日元 |
| GBP | 英镑 |
| EUR | 欧元 |
| AUD | 澳元 |
| SGD | 新加坡元 |

---

### 编辑账户

```http
POST /accounts/<int:account_id>/edit
```

**说明**: 需登录状态。仅账户所有者或成人可编辑。

**参数**: 同添加账户，所有参数可选（仅更新提供的字段）

---

### 删除账户

```http
POST /accounts/<int:account_id>/delete
```

**说明**: 需登录状态。仅账户所有者或成人可删除。

---

## 分类接口

### 分类列表

```http
GET /categories
```

**说明**: 需登录状态。按类型→大类→子类→名称排序。

---

### 添加分类

```http
POST /categories/add
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category_name | string | 是 | 分类名称 |
| category_type | string | 是 | 类型：I/E/T/S |
| category_class | string | 是 | 大类 |
| category_subclass | string | 否 | 子类 |
| category_other_name | string | 否 | 别名 |
| csrf_token | string | 是 | CSRF 令牌 |

---

### 编辑分类

```http
POST /categories/<int:category_id>/edit
```

**参数**: 同添加分类，所有参数可选

---

### 删除分类

```http
POST /categories/<int:category_id>/delete
```

**说明**: 需登录状态。

---

## 家庭接口

### 家庭管理页面

```http
GET /family
```

**说明**: 需登录状态，仅成人可访问。

**响应数据**:

| 字段 | 类型 | 说明 |
|------|------|------|
| family | object | 家庭信息 |
| members | list | 成员列表 |
| users | list | 用户列表 |

---

### 添加家庭成员

```http
POST /family/add-member
```

**说明**: 需登录状态，仅成人可操作。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| owner_name | string | 是 | 成员称呼 |
| username | string | 是 | 登录用户名 |
| password | string | 是 | 密码（至少8字符） |
| role | string | 是 | 角色：ADULT/CHILD |
| csrf_token | string | 是 | CSRF 令牌 |

---

### 编辑成员

```http
POST /family/edit-member/<int:owner_id>
```

**说明**: 需登录状态，仅成人可操作。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| owner_name | string | 是 | 成员称呼 |
| role | string | 是 | 角色：ADULT/CHILD |
| csrf_token | string | 是 | CSRF 令牌 |

---

### 删除成员

```http
POST /family/delete-member/<int:owner_id>
```

**说明**: 需登录状态，仅成人可操作。不能删除自己。家庭至少保留一位成人。

---

### 重置成员密码

```http
POST /family/reset-password/<int:owner_id>
```

**说明**: 需登录状态，仅成人可操作。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| new_password | string | 是 | 新密码（至少8字符） |
| csrf_token | string | 是 | CSRF 令牌 |

---

## 常用筛选组合示例

### 查看本月所有未核对交易

```
GET /?status=UNVERIFIED&tab=list-tab
```

### 查看特定分类的支出

```
GET /?category_id=3&tab=list-tab
```

### 查看特定账户的交易

```
GET /?account_id=1&tab=list-tab
```

### 查看上月已核对交易

```
GET /?start_date=2026-04-01&end_date=2026-04-30&status=VERIFIED&tab=list-tab
```

### 组合筛选

```
GET /?start_date=2026-05-01&end_date=2026-05-31&status=UNVERIFIED&category_id=2&account_id=1&tab=list-tab
```

---

## 错误处理

### 认证错误

| 场景 | 响应 |
|------|------|
| 未登录访问受保护页面 | 重定向到 `/login`，Flash: "请先登录以访问此页面。" |
| 用户名或密码错误 | 重定向回 `/login`，Flash: "用户名或密码错误" |
| 注册验证失败 | 重定向回 `/register`，Flash 显示具体验证错误 |

### 权限错误

| 场景 | 响应 |
|------|------|
| 小孩访问家庭管理 | 重定向到仪表盘，Flash: "仅成人可以管理家庭成员" |
| 操作他人交易 | 重定向，Flash: "无权操作此交易" |
| 删除自己 | 重定向，Flash: "不能删除自己" |

### 数据验证错误

| 场景 | 响应 |
|------|------|
| 必填字段为空 | 重定向，Flash: "请填写完整信息" |
| 金额≤0 | 重定向，Flash: "金额必须大于0" |
| 转账账户相同 | 重定向，Flash: "请选择不同的转出和转入账户" |
| 无效状态 | 重定向，Flash: "无效的状态" |

---

**最后更新**：2026年5月5日