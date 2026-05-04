## 运行测试

#### 安装测试依赖后执行：

```bash
# 安装测试依赖
pip install -r requirements-dev.txt

# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_models.py -v

# 运行带覆盖率报告
pytest tests/ --cov=app --cov-report=html

```

#### 测试用例内容：

以下是每个测试文件的用例清单：

---

## `tests/conftest.py` - 测试配置（8个fixture）

| Fixture | 说明 |
|---------|------|
| `app` | 创建测试Flask应用，使用临时SQLite数据库 |
| `client` | 创建测试HTTP客户端 |
| `test_user` | 创建测试用户（含家庭和Owner），返回 user_id |
| `logged_in_client` | 创建已登录的测试客户端 |
| `test_owner` | 返回测试用户的 owner_id |
| `test_family` | 返回测试用户的 family_id |
| `test_account` | 创建测试账户，返回 account_id |
| `test_category` | 创建测试分类，返回 category_id |
| `test_transaction` | 创建测试交易，返回 trans_id |

---

好的，以下是修正后的完整测试用例清单（53个用例全部通过）：

---

## `tests/test_models.py` - 模型测试（16个用例）

### TestUserModel（4个）
| 用例 | 说明 |
|------|------|
| `test_create_user` | 创建用户并验证属性 |
| `test_child_user` | 小孩用户 is_adult() 返回 False |
| `test_password_verification` | 密码验证正确/错误 |
| `test_unique_username` | 用户名唯一性约束 |

### TestFamilyModel（2个）
| 用例 | 说明 |
|------|------|
| `test_create_family` | 创建家庭并验证属性 |
| `test_family_members_relationship` | 用户与家庭的关联关系 |

### TestOwnerModel（1个）
| 用例 | 说明 |
|------|------|
| `test_create_owner` | 创建Owner并验证关联 |

### TestAccountModel（2个）
| 用例 | 说明 |
|------|------|
| `test_create_account` | 创建账户并验证属性 |
| `test_account_close_date` | 账户关闭日期设置 |

### TestCategoryModel（3个）
| 用例 | 说明 |
|------|------|
| `test_create_category` | 创建分类并验证类型枚举 |
| `test_category_with_alias` | 分类别名设置 |
| `test_category_types` | 四种分类类型（I/E/T/S）枚举值 |

### TestTransactionModel（4个）
| 用例 | 说明 |
|------|------|
| `test_create_income` | 收入交易 is_income()=True |
| `test_create_expense` | 支出交易 is_expense()=True |
| `test_create_transfer` | 转账交易配对逻辑 |
| `test_transaction_currency` | 交易货币设置 |

---

## `tests/test_auth.py` - 认证测试（10个用例）

| 用例 | 说明 |
|------|------|
| `test_login_page` | 登录页面加载 |
| `test_register_page` | 注册页面加载 |
| `test_register_success` | 成功注册并验证数据库 |
| `test_register_empty_username` | 空用户名注册 |
| `test_register_short_password` | 短密码注册 |
| `test_register_duplicate_username` | 重复用户名注册 |
| `test_login_success` | 成功登录 |
| `test_login_wrong_password` | 错误密码登录 |
| `test_logout` | 退出登录 |
| `test_protected_route_redirect` | 未登录访问受保护页面重定向 |

---

## `tests/test_accounts.py` - 账户测试（6个用例）

| 用例 | 说明 |
|------|------|
| `test_accounts_page` | 账户管理页面加载 |
| `test_add_account` | 添加账户并验证数据库 |
| `test_add_account_empty_name` | 空名称添加账户 |
| `test_edit_account` | 编辑账户名称 |
| `test_delete_account` | 删除账户 |
| `test_accounts_unauthenticated` | 未登录访问重定向 |

---

## `tests/test_categories.py` - 分类测试（7个用例）

| 用例 | 说明 |
|------|------|
| `test_categories_page` | 分类管理页面加载 |
| `test_add_category` | 添加支出分类 |
| `test_add_category_with_alias` | 添加带别名的分类 |
| `test_add_income_category` | 添加收入分类 |
| `test_edit_category` | 编辑分类名称 |
| `test_delete_category` | 删除分类 |
| `test_categories_unauthenticated` | 未登录访问重定向 |

---

## `tests/test_transactions.py` - 交易测试（6个用例）

| 用例 | 说明 |
|------|------|
| `test_dashboard` | 仪表盘页面加载 |
| `test_add_income` | 添加收入交易 |
| `test_add_expense` | 添加支出交易（金额为负） |
| `test_add_transfer` | 添加转账交易（生成两条配对记录） |
| `test_delete_transaction` | 删除交易 |
| `test_dashboard_unauthenticated` | 未登录访问重定向 |

---

## `tests/test_family.py` - 家庭测试（8个用例）

| 用例 | 说明 |
|------|------|
| `test_family_page` | 家庭管理页面加载 |
| `test_add_member` | 添加小孩成员 |
| `test_add_adult_member` | 添加成人成员 |
| `test_edit_member` | 编辑成员信息 |
| `test_delete_member` | 删除成员 |
| `test_cannot_delete_self` | 不能删除自己 |
| `test_reset_password` | 重置成员密码 |
| `test_family_unauthenticated` | 未登录访问重定向 |

---

## 汇总

| 文件 | 用例数 |
|------|--------|
| `test_models.py` | 16 |
| `test_auth.py` | 10 |
| `test_accounts.py` | 6 |
| `test_categories.py` | 7 |
| `test_transactions.py` | 6 |
| `test_family.py` | 8 |
| **总计** | **53** ✅ |