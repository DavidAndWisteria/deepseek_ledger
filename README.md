# 💰 Personal Ledger - 个人财务管理系统

![Version](https://img.shields.io/badge/version-0.2.8-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-105%20passed-brightgreen)

一个安全、轻量级的个人及家庭财务管理应用，支持收支记录、转账、分类统计、状态核对等功能。

## ✨ 功能特点

- 🔐 **安全可靠**：密码bcrypt加密、CSRF保护、XSS防护、SQL注入防护
- 📊 **收支管理**：记录收入、支出和转账，自动计算结余
- 👨‍👩‍👧‍👦 **家庭管理**：支持多成员家庭，成人/小孩权限隔离
- ✅ **状态核对**：交易状态管理（未核对/已核对/有疑问），支持批量核对
- 📈 **数据统计**：按日期、分类、账户、状态等维度筛选统计
- 🎨 **界面友好**：响应式设计，浅色调UI，支持移动端访问
- 💾 **数据导入**：支持 Bluecoins CSV 导入（账户/分类/交易），预览与手动映射，自动去重
- 💾 **本地运行**：SQLite数据库，无需额外配置，启动自动迁移
- 🚀 **轻量高效**：Flask框架，资源占用低
- 🧪 **测试完善**：105个测试用例，测试与开发环境完全隔离

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip
- Git（可选）

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://github.com/DavidAndWisteria/deepseek_ledger.git
cd deepseek_ledger
```

#### 2. 创建虚拟环境（推荐）

```bash
# Linux/Mac
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
# Linux/Mac
cp .env.example .env

# Windows
copy .env.example .env
```

然后编辑 `.env` 文件，修改 `SECRET_KEY`：

```bash
SECRET_KEY=your-random-secret-key-here
```

生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 5. 运行应用

```bash
python run.py
```

访问 http://127.0.0.1:5000

#### 6. 创建账户

首次使用需注册：
1. 填写家庭名称
2. 填写你的称呼
3. 选择角色（成人可看全家数据，小孩仅看自己）
4. 设置用户名和密码

## 📸 界面展示

### 仪表盘
- 筛选区：按日期、状态、分类、账户筛选交易
- 统计卡片：总收入、总支出、转账金额、净收入、待核对数量
- 添加交易：支持收入/支出/转账，时间精确到分钟，一键填入当前时间
- 交易列表：显示日期时间、类型、账户、分类、金额、状态，支持编辑/核对/标记/删除

### 账户管理
- 添加账户：类型（现金/储蓄/信用卡等）、机构、货币、创建/关闭日期
- 账户拥有者：支持为家庭成员创建账户
- 列表按 类型·机构·拥有者·名称 排序

### 分类管理
- 分类类型：收入/支出/转账/特殊
- 层级结构：大类 › 子类 › 名称
- 支持别名设置

### 家庭管理
- 成员列表：显示角色、状态、加入时间
- 成人可添加/编辑/删除成员、重置密码
- 权限说明展示

## 🏗️ 技术栈

### 后端
- **框架**: Flask 3.0
- **ORM**: SQLAlchemy 3.1
- **认证**: Flask-Login 0.6
- **安全**: Flask-WTF 1.2
- **密码加密**: bcrypt 4.1

### 前端
- **基础**: HTML5 + CSS3
- **交互**: Vanilla JavaScript
- **模板**: Jinja2
- **UI**: 自定义响应式设计，浅色调

### 数据库
- **开发**: SQLite 3
- **特点**: 无需安装，启动自动迁移

### 安全措施
- **密码存储**: bcrypt哈希（12轮加密）
- **会话保护**: HTTPOnly Cookie
- **CSRF防护**: Flask-WTF CSRF令牌
- **XSS防护**: 输入清理 + 模板自动转义
- **SQL注入防护**: ORM参数化查询
- **输入验证**: 前后端双重验证
- **权限控制**: 成人/小孩数据隔离

## 📁 项目结构

```
deepseek_ledger/
├── app/                          # 应用主目录
│   ├── __init__.py               # 应用初始化（含数据库自动迁移）
│   ├── models.py                 # 数据库模型（11个表）
│   ├── routes/                   # 路由模块
│   │   ├── __init__.py
│   │   ├── auth.py              # 认证（注册/登录/登出）
│   │   ├── transactions.py      # 交易（CRUD/状态管理/批量核对）
│   │   ├── accounts.py          # 账户管理
│   │   ├── categories.py        # 分类管理
│   │   ├── family.py            # 家庭管理
│   │   ├── importer.py          # Bluecoins 数据导入
│   │   ├── data_manager.py      # 数据备份/恢复/查询
│   │   └── records.py           # 历史记录（deprecated）
│   ├── services/                 # 业务逻辑
│   │   └── import_service.py    # 导入引擎（解析/匹配/创建）
│   └── templates/                # HTML模板
│       ├── base.html            # 基础布局
│       ├── login.html           # 登录页
│       ├── register.html        # 注册页
│       ├── dashboard.html       # 仪表盘（筛选/统计/交易）
│       ├── accounts.html        # 账户管理
│       ├── categories.html      # 分类管理
│       ├── family.html          # 家庭管理
│       ├── import.html          # 数据导入
│       └── data_manager.html    # 数据管理
├── tests/                        # 测试目录（105个用例）
│   ├── conftest.py              # 测试配置（临时数据库隔离）
│   ├── test_models.py           # 模型测试
│   ├── test_auth.py             # 认证测试
│   ├── test_accounts.py         # 账户测试
│   ├── test_categories.py       # 分类测试
│   ├── test_transactions.py     # 交易测试
│   ├── test_family.py           # 家庭测试
│   ├── test_import_account.py   # 导入账户测试
│   └── test_import_category.py  # 导入分类测试
├── docs/                         # 文档目录
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git忽略文件
├── LICENSE                       # MIT许可证
├── README.md                     # 项目说明（本文件）
├── CHANGELOG.md                  # 更新日志
├── CONTRIBUTING.md               # 贡献指南
├── requirements.txt              # 项目依赖
├── requirements-dev.txt          # 开发依赖
└── run.py                        # 应用入口
```

## 🗄️ 数据库设计

### 核心表

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| family | 家庭 | family_id, family_name |
| user | 用户 | id, username, role(ADULT/CHILD) |
| owner | 所有者 | owner_id, owner_name |
| account | 账户 | account_id, account_type, account_custodian |
| category | 分类 | category_id, category_type(I/E/T/S) |
| transaction | 交易 | trans_id, trans_amount, trans_status |
| bluecoins_account_mapping | 账户映射 | bluecoins_name, account_id, is_manual |
| bluecoins_category_mapping | 分类映射 | 五元组(year/type/group/category/title), category_id, is_manual |

### 交易状态

| 状态 | 说明 |
|------|------|
| UNVERIFIED | 未核对（默认） |
| VERIFIED | 已核对 |
| FLAGGED | 有疑问 |
| RECONCILED | 已对账 |

## 📖 API 接口

### 认证相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /login | 登录页面 |
| POST | /login | 登录请求 |
| GET | /register | 注册页面 |
| POST | /register | 注册请求 |
| GET | /logout | 退出登录 |

### 交易相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 仪表盘（支持筛选参数） |
| POST | /add | 添加交易 |
| POST | /delete/\<id\> | 删除交易 |
| POST | /edit/\<id\> | 编辑交易 |
| POST | /status/\<id\>/\<status\> | 更新交易状态 |
| POST | /batch-verify | 批量核对 |

### 账户相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /accounts | 账户列表 |
| POST | /accounts/add | 添加账户 |
| POST | /accounts/\<id\>/edit | 编辑账户 |
| POST | /accounts/\<id\>/delete | 删除账户 |

### 分类相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /categories | 分类列表 |
| POST | /categories/add | 添加分类 |
| POST | /categories/\<id\>/edit | 编辑分类 |
| POST | /categories/\<id\>/delete | 删除分类 |

### 家庭相关

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /family | 家庭管理页面 |
| POST | /family/add-member | 添加成员 |
| POST | /family/edit-member/\<id\> | 编辑成员 |
| POST | /family/delete-member/\<id\> | 删除成员 |
| POST | /family/reset-password/\<id\> | 重置成员密码 |

### 数据导入 (Bluecoins)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /import | 导入页面 |
| POST | /import/accounts | 导入账户 CSV |
| POST | /import/categories | 导入分类 CSV |
| POST | /import/transactions/upload | 上传交易 CSV 预览 |
| POST | /import/transactions/confirm | 确认导入（含手动映射） |
| GET | /import/download-skipped | 下载跳过的交易 CSV |

### 数据管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /data | 数据管理页面 |
| POST | /data/backup | 备份数据库 |
| POST | /data/restore | 恢复数据库 |
| POST | /data/query | 执行查询 |

### 筛选参数（仪表盘）

| 参数 | 类型 | 说明 |
|------|------|------|
| start_date | date | 开始日期 |
| end_date | date | 结束日期 |
| status | string | 状态筛选 |
| category_id | int | 分类筛选 |
| account_id | int | 账户筛选 |
| tab | string | 当前标签页 |

## 🧪 测试

### 运行所有测试

```bash
# 安装测试依赖
pip install -r requirements-dev.txt

# 运行测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

### 测试覆盖范围

| 模块 | 用例数 |
|------|--------|
| 模型测试 | 19 |
| 认证测试 | 10 |
| 账户测试 | 6 |
| 分类测试 | 7 |
| 交易测试 | 20 |
| 家庭测试 | 8 |
| 导入账户 | 17 |
| 导入分类 | 13 |
| 其他 | 5 |
| **总计** | **105** |

## 📝 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解每个版本的详细更新。

### 最新版本 v0.2.8

- 🐛 修复交易导入手动匹配分类 bug（key 格式、年份提取、映射优先级、重复插入）
- 🐛 修复 `_match_owner()` 兜底逻辑与文档不一致
- 🔧 移除八达通交易分类特殊处理，统一精确匹配
- ✨ 创建新分类表单添加别名字段
- 🐛 修复测试数据库隔离（`create_app` 支持 `test_config`）
- ✅ 105 个测试用例全部通过

## 🗺️ 路线图

### 短期计划 (v0.2.x)
- [x] 数据导入功能（Bluecoins CSV）
- [x] 导入预览与手动映射
- [x] 数据备份与恢复
- [ ] 图表统计分析（饼图/折线图）
- [ ] 仪表盘首页显示账户余额
- [ ] 数据导出功能（CSV/Excel）

### 中期计划 (v0.3.x)
- [ ] 定期存款管理
- [ ] 货币转换
- [ ] 预算设置与管理
- [ ] 定期财务报告
- [ ] 数据备份与恢复

### 长期计划 (v1.0.x)
- [ ] 多币种支持完善
- [ ] API 接口完善
- [ ] 移动 APP 版本
- [ ] 数据云同步（可选）

## ❓ 常见问题

### Q: 忘记密码怎么办？
A: 成人用户可在家庭管理页面为其他成员重置密码。自己的密码忘记需要手动操作数据库。

### Q: 如何备份数据？
A: 备份 `instance/ledger.db` 文件即可。

### Q: 可以多人使用吗？
A: 支持多用户家庭，成人可查看全家数据，小孩仅看自己数据。

### Q: 数据存储在哪里？
A: 所有数据存储在本地 SQLite 数据库文件中（`instance/ledger.db`）。

### Q: 如何迁移到其他电脑？
A: 复制整个项目文件夹，包括 `instance/ledger.db` 文件即可。

### Q: 测试会影响开发数据吗？
A: 不会。测试使用临时数据库，且 pytest 启动时自动备份开发数据库，结束时恢复。

## ⚠️ 安全注意事项

1. **修改默认密钥**：务必修改 `.env` 中的 `SECRET_KEY`
2. **本地使用**：建议仅在本地或受信任的网络中使用
3. **定期备份**：定期备份 `instance/ledger.db` 文件
4. **强密码**：使用强密码保护账户
5. **系统更新**：保持 Python 和依赖包为最新版本

## 📄 许可证

本项目基于 MIT 许可证开源。详见 [LICENSE](LICENSE) 文件。

## 🌟 致谢

感谢以下开源项目：
- [Flask](https://flask.palletsprojects.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Flask-Login](https://flask-login.readthedocs.io/)
- [bcrypt](https://github.com/pyca/bcrypt/)

---

<div align="center">
  <p>如果这个项目对你有帮助，请给一个 ⭐ Star！</p>
  <p>Made with ❤️ for personal finance management</p>
</div>