# 安全说明文档

---

## 概述

本项目实现了多层安全防护措施，确保个人财务数据的安全性。以下详细说明各项安全措施及其实现方式。

---

## 1. 认证安全

### 1.1 密码安全

| 措施 | 实现 | 说明 |
|------|------|------|
| 哈希算法 | bcrypt (12轮) | 使用 `bcrypt.hashpw(password, gensalt(12))` |
| 盐值 | 随机生成 | 每次哈希自动生成唯一盐值 |
| 明文存储 | 禁止 | 密码仅存储哈希值，从不存储明文 |
| 密码验证 | 恒定时间比较 | `bcrypt.checkpw()` 防时序攻击 |

**代码示例**:
```python
# 设置密码
def set_password(self, password):
    self.password_hash = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=12)
    ).decode('utf-8')

# 验证密码
def check_password(self, password):
    return bcrypt.checkpw(
        password.encode('utf-8'),
        self.password_hash.encode('utf-8')
    )
```

### 1.2 密码强度要求

| 要求 | 说明 |
|------|------|
| 最小长度 | 8 字符 |
| 复杂度 | 无强制特殊字符要求（可后续增强） |
| 用户名限制 | 3-80 字符，仅字母、数字、下划线 |

### 1.3 账户锁定

当前版本未实现登录失败锁定。建议后续版本添加：
- 连续失败 5 次后锁定 30 分钟
- 密码重置功能

---

## 2. 会话安全

### 2.1 Cookie 配置

| 配置 | 值 | 说明 |
|------|------|------|
| `SESSION_COOKIE_HTTPONLY` | True | 禁止 JavaScript 读取 Cookie |
| `SESSION_COOKIE_SAMESITE` | 'Lax' | 防止 CSRF 攻击 |
| `SECRET_KEY` | 环境变量 | 签名会话 Cookie 的密钥 |

**代码**:
```python
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
```

### 2.2 会话管理

| 措施 | 说明 |
|------|------|
| Flask-Login | 管理用户会话生命周期 |
| 登出 | 清除服务端会话 |
| 测试隔离 | 测试使用独立 SECRET_KEY |

---

## 3. CSRF 防护

### 3.1 实现方式

使用 Flask-WTF 的 CSRF 保护：

```python
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()
csrf.init_app(app)
```

### 3.2 防护范围

| 保护内容 | 说明 |
|------|------|
| 所有 POST 请求 | 必须携带有效 CSRF 令牌 |
| 表单提交 | 模板中使用 `{{ csrf_token() }}` |
| 测试环境 | `WTF_CSRF_ENABLED = False`（不影响开发数据库） |

### 3.3 令牌验证

```html
<!-- 每个表单必须包含 -->
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

---

## 4. XSS 防护

### 4.1 多层防护

| 层级 | 措施 | 说明 |
|------|------|------|
| 输入层 | bleach 清理 | 移除 HTML 标签 |
| 模板层 | Jinja2 自动转义 | `{{ }}` 默认转义特殊字符 |
| 输出层 | 长度限制 | 字符串截断防止超长输入 |

### 4.2 输入清理

```python
import bleach

def sanitize_input(text):
    """清理用户输入，移除所有 HTML 标签"""
    if text:
        return bleach.clean(text, tags=[], strip=True)[:200]
    return ''
```

### 4.3 模板自动转义

```html
<!-- 安全：自动转义 -->
{{ user_input }}

<!-- 仅在确认安全时使用 |safe -->
{{ trusted_html|safe }}
```

---

## 5. SQL 注入防护

### 5.1 ORM 参数化查询

所有数据库操作通过 SQLAlchemy ORM，自动使用参数化查询：

```python
# 安全：参数化查询（SQLAlchemy 2.0 风格）
from sqlalchemy import select
db.session.scalars(select(User).where(User.username == username)).first()
db.session.get(User, user_id)

# 禁止：字符串拼接
# db.session.execute(f"SELECT * FROM user WHERE username='{username}'")  # 危险！

### 5.2 查询构建

```python
# 动态查询构建也是安全的
query = Transaction.query
if start_date:
    query = query.filter(Transaction.trans_datetime >= start_date)
if category_id:
    query = query.filter_by(trans_category_id=category_id)
```

---

## 6. 权限控制

### 6.1 角色模型

| 角色 | 权限 |
|------|------|
| ADULT（成人） | 查看家庭所有数据、管理成员、管理账户/分类 |
| CHILD（小孩） | 仅查看自己的交易和账户 |

### 6.2 数据隔离

```python
def get_visible_transactions_query(...):
    if current_user.can_view_family_data():
        # 成人：查询家庭所有交易
        family_owner_ids = [...]
        query = query.filter(Transaction.trans_owner_id.in_(family_owner_ids))
    else:
        # 小孩：仅查询自己的交易
        query = query.filter_by(trans_owner_id=owner.owner_id)
```

### 6.3 操作权限检查

每个修改操作都验证所有者身份：

```python
# 编辑交易前检查权限
if transaction.trans_owner_id != owner.owner_id:
    flash('无权操作此交易')
    return redirect(...)
```

### 6.4 路由保护

```python
# 所有敏感路由需要登录
@login_required
def add_transaction():
    ...

# 家庭管理仅成人可访问
if not current_user.is_adult():
    flash('仅成人可以管理家庭成员')
    return redirect(...)
```

---

## 7. 输入验证

### 7.1 前端验证

| 验证项 | 实现 |
|------|------|
| 必填字段 | `required` 属性 |
| 长度限制 | `minlength`, `maxlength` |
| 格式限制 | `pattern` 正则表达式 |
| 数值范围 | `min`, `max`, `step` |
| 用户名格式 | `[a-zA-Z0-9_]{3,80}` |

### 7.2 后端验证

| 验证项 | 实现 |
|------|------|
| 空值检查 | `if not field:` |
| 金额范围 | 0 < amount ≤ 99999999.99 |
| 日期格式 | `datetime.strptime()` 异常捕获 |
| 枚举值 | `Enum(value)` 异常捕获 |
| 字符串长度 | 截断处理 |

---

## 8. 错误处理

### 8.1 安全错误响应

| 原则 | 说明 |
|------|------|
| 不泄露内部结构 | 500 错误不显示数据库细节 |
| 统一错误消息 | 登录失败显示"用户名或密码错误"（不区分） |
| Flash 消息 | 用户友好的中文提示 |
| 调试模式 | `debug=True` 仅开发环境 |

### 8.2 异常处理

```python
try:
    trans_datetime = datetime.strptime(date_str, '%Y-%m-%d')
except ValueError:
    trans_datetime = datetime.now(timezone.utc)  # 默认值
```

---

## 9. 文件安全

### 9.1 敏感文件

| 文件 | 保护措施 |
|------|---------|
| `.env` | `.gitignore` 排除，不提交到版本控制 |
| `instance/ledger.db` | `.gitignore` 排除 |
| `SECRET_KEY` | 通过环境变量加载，有默认值但建议修改 |

### 9.2 .gitignore 配置

```
.env
instance/
*.db
*.sqlite
```

---

## 10. 依赖安全

### 10.1 依赖清单

| 包 | 版本 | 用途 |
|------|------|------|
| Flask | 3.0.0 | Web 框架 |
| Flask-SQLAlchemy | 3.1.1 | ORM |
| Flask-Login | 0.6.3 | 会话管理 |
| Flask-WTF | 1.2.1 | CSRF 保护 |
| bcrypt | 4.1.2 | 密码哈希 |
| bleach | 6.1.0 | HTML 清理 |
| Werkzeug | 3.0.1 | WSGI 工具 |

### 10.2 安全更新

定期运行以下命令检查已知漏洞：

```bash
pip install safety
safety check
```

---

## 11. 测试安全

### 11.1 测试隔离

| 措施 | 说明 |
|------|------|
| 独立数据库 | 测试使用临时 SQLite 文件，通过 `create_app(test_config={...})` 在 engine 初始化前注入 |
| 独立 SECRET_KEY | 测试使用独立密钥 |
| 数据库备份 | pytest 启动时自动备份开发数据库 |
| 数据库恢复 | pytest 结束时自动恢复 |
| CSRF 关闭 | 测试环境 `WTF_CSRF_ENABLED = False` |

### 11.2 安全测试用例

| 测试 | 覆盖内容 |
|------|---------|
| `test_password_not_stored_plaintext` | 密码不存储明文 |
| `test_password_hash_unique_per_user` | 相同密码产生不同哈希 |
| `test_xss_sanitization` | XSS 输入被清理 |
| `test_user_data_isolation` | 用户数据隔离 |
| `test_csrf_protection_enabled` | CSRF 保护已启用 |

---

## 12. 安全清单

### 部署前检查

- [ ] 修改 `.env` 中的 `SECRET_KEY` 为随机值
- [ ] 确认 `debug=False`（生产环境）
- [ ] 确认数据库文件权限正确
- [ ] 确认仅本地网络访问（`host='127.0.0.1'`）
- [ ] 检查依赖包版本是否为最新安全版本
- [ ] 运行 `pytest tests/` 确保所有测试通过

### 持续维护

- [ ] 定期备份 `instance/ledger.db`
- [ ] 定期更新 Python 和依赖包
- [ ] 检查 GitHub Security Advisories
- [ ] 审查访问日志（如适用）

---

## 13. 已知限制

| 限制 | 影响 | 计划 |
|------|------|------|
| 无账户锁定 | 暴力破解风险 | v0.2.x |
| 无密码重置 | 忘记密码需手动处理 | v0.2.x |
| 无 2FA | 单一认证因素 | 远期 |
| 无 HTTPS | 仅本地使用无影响 | 如部署公网需添加 |
| 无审计日志 | 无法追溯操作历史 | v0.3.x |

---

**最后更新**：2026年6月10日