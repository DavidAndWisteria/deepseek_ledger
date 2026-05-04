好的，我明白了。以下是完整、可一键复制的 README.md 内容：

# 💰 Personal Ledger - 个人账本管理系统

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Security](https://img.shields.io/badge/security-bcrypt%20%7C%20CSRF%20%7C%20XSS-brightgreen)

一个安全、轻量级的个人财务管理应用，支持收支记录、分类统计和数据导出。

## ✨ 功能特点

- 🔐 **安全可靠**：密码bcrypt加密、CSRF保护、XSS防护、SQL注入防护
- 📊 **收支管理**：记录收入和支出，自动计算结余
- 📈 **数据统计**：按分类、时间等维度统计财务数据
- 🎨 **界面友好**：响应式设计，支持移动端访问
- 💾 **本地运行**：SQLite数据库，无需额外配置
- 🚀 **轻量高效**：Flask框架，资源占用低

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip
- Git（可选）

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/personal-ledger.git
cd personal-ledger
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

然后编辑 `.env` 文件，修改以下配置：

```bash
SECRET_KEY=your-random-secret-key-here
```

生成随机密钥的方法：

```bash
# Linux/Mac
python -c "import secrets; print(secrets.token_hex(32))"

# Windows
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 5. 初始化数据库

```bash
python scripts/init_db.py
```

#### 6. 运行应用

```bash
python run.py
```

访问 http://127.0.0.1:5000

#### 7. 创建账户

打开浏览器访问 http://127.0.0.1:5000/register 创建你的账户即可开始使用。

## 📸 界面展示

### 仪表盘
显示总收入、支出、结余，以及最近的交易记录。

### 添加记录
- 选择记录类型（收入/支出）
- 输入金额
- 选择或输入分类
- 添加备注（可选）
- 选择日期

### 记录管理
- 查看所有记录
- 删除不需要的记录
- 按分类筛选
- 按日期排序

## 🏗️ 技术栈

### 后端
- **框架**: Flask 2.3.3
- **ORM**: SQLAlchemy 3.0.5
- **认证**: Flask-Login 0.6.2
- **安全**: Flask-WTF 1.2.1
- **密码加密**: bcrypt 4.0.1

### 前端
- **基础**: HTML5 + CSS3
- **交互**: Vanilla JavaScript
- **模板**: Jinja2
- **UI**: 自定义响应式设计

### 数据库
- **开发**: SQLite 3
- **特点**: 无需安装，零配置

### 安全措施
- **密码存储**: bcrypt哈希（12轮加密）
- **会话保护**: HTTPOnly Cookie
- **CSRF防护**: Flask-WTF CSRF令牌
- **XSS防护**: 输入清理 + 模板自动转义
- **SQL注入防护**: ORM参数化查询
- **输入验证**: 前后端双重验证
- **权限控制**: 用户数据隔离

## 📁 项目结构

```
personal-ledger/
├── app/                          # 应用主目录
│   ├── __init__.py               # 应用初始化
│   ├── config.py                 # 配置文件
│   ├── models.py                 # 数据库模型
│   ├── routes/                   # 路由模块
│   │   ├── __init__.py
│   │   ├── auth.py              # 认证相关路由
│   │   └── records.py           # 记录相关路由
│   ├── services/                 # 业务逻辑层
│   │   ├── __init__.py
│   │   └── record_service.py
│   ├── utils/                    # 工具函数
│   │   ├── __init__.py
│   │   ├── validators.py        # 验证器
│   │   └── security.py          # 安全工具
│   ├── static/                   # 静态文件
│   │   ├── css/
│   │   │   └── style.css
│   │   ├── js/
│   │   │   └── main.js
│   │   └── images/
│   └── templates/                # HTML模板
│       ├── base.html
│       ├── dashboard.html
│       ├── login.html
│       └── register.html
├── tests/                        # 测试目录
│   ├── __init__.py
│   ├── conftest.py              # 测试配置
│   ├── test_models.py           # 模型测试
│   ├── test_auth.py             # 认证测试
│   └── test_records.py          # 记录测试
├── docs/                         # 文档目录
│   ├── API.md                   # API文档
│   ├── DATABASE.md              # 数据库文档
│   └── SECURITY.md              # 安全说明
├── scripts/                      # 脚本工具
│   ├── init_db.py               # 数据库初始化
│   └── backup.sh                # 数据备份
├── .github/                      # GitHub配置
│   └── workflows/
│       └── python-app.yml       # CI/CD配置
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git忽略文件
├── LICENSE                       # 许可证
├── README.md                     # 项目说明（本文件）
├── CHANGELOG.md                  # 更新日志
├── CONTRIBUTING.md               # 贡献指南
├── requirements.txt              # 项目依赖
├── requirements-dev.txt          # 开发依赖
├── setup.py                      # 安装配置
└── run.py                        # 应用入口
```

## 🗄️ 数据库设计

### 用户表 (User)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键，自增 |
| username | String(80) | 用户名，唯一索引 |
| password_hash | String(120) | bcrypt密码哈希 |
| created_at | DateTime | 创建时间 |

### 记录表 (Record)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键，自增 |
| user_id | Integer | 外键，关联用户 |
| amount | Float | 金额 |
| category | String(50) | 分类 |
| description | String(200) | 备注说明 |
| record_type | String(10) | 类型（income/expense） |
| date | DateTime | 记录日期 |

详细数据库文档请查看 [DATABASE.md](docs/DATABASE.md)

## 📖 API 接口

### 认证相关
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /login | 登录页面 |
| POST | /login | 登录请求 |
| GET | /register | 注册页面 |
| POST | /register | 注册请求 |
| GET | /logout | 退出登录 |

### 记录相关
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 仪表盘 |
| POST | /add_record | 添加记录 |
| POST | /delete_record/<id> | 删除记录 |

详细API文档请查看 [API.md](docs/API.md)

## 🧪 测试

### 运行所有测试

```bash
# 安装测试依赖
pip install -r requirements-dev.txt

# 运行测试
pytest tests/

# 带覆盖率报告
pytest tests/ --cov=app --cov-report=html
```

### 测试覆盖范围
- ✅ 用户注册/登录
- ✅ 认证中间件
- ✅ 记录的CRUD操作
- ✅ 输入验证
- ✅ 安全防护措施
- ✅ 权限控制

## 🐳 Docker 部署（可选）

### 使用 Docker 构建

```bash
# 构建镜像
docker build -t personal-ledger .

# 运行容器
docker run -p 5000:5000 -v $(pwd)/instance:/app/instance personal-ledger
```

### 使用 Docker Compose

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 🔧 开发指南

### 代码风格
- 遵循 PEP 8 规范
- 使用 Black 进行代码格式化
- 使用 Flake8 进行代码检查
- 使用 Bandit 进行安全扫描

### 提交规范
使用约定式提交信息：

```
feat: 添加新功能
fix: 修复bug
docs: 更新文档
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具相关
```

### 分支管理
- `main`: 生产环境代码
- `develop`: 开发分支
- `feature/*`: 功能分支
- `bugfix/*`: 修复分支

## 📝 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解每个版本的详细更新。

### 最新版本 v1.0.0
- ✨ 用户注册与登录系统
- ✨ 收支出记录管理
- ✨ 基础仪表盘界面
- ✨ 自动计算结余
- 🔒 完整的安全防护措施
- 📱 响应式界面设计

## 🗺️ 路线图

### 短期计划
- [ ] 数据导出功能（CSV/Excel）
- [ ] 图表统计分析（饼图/折线图）
- [ ] 记录编辑功能
- [ ] 分类管理

### 中期计划
- [ ] 预算设置与管理
- [ ] 定期财务报告
- [ ] 数据备份与恢复
- [ ] 导入银行账单

### 长期计划
- [ ] 多币种支持
- [ ] API接口完善
- [ ] 移动APP版本

## ❓ 常见问题

### Q: 忘记密码怎么办？
A: 目前版本需要手动重置数据库。后续版本会添加密码重置功能。临时解决方案：
```bash
python scripts/reset_password.py --username your_username --new-password new_password
```

### Q: 如何备份数据？
A: 备份 `instance/ledger.db` 文件即可：
```bash
# Linux/Mac
cp instance/ledger.db instance/ledger_backup_$(date +%Y%m%d).db

# 或使用提供的备份脚本
./scripts/backup.sh
```

### Q: 可以多人使用吗？
A: 当前版本支持多用户账户，每个用户的数据是隔离的。

### Q: 数据存储在哪里？
A: 所有数据存储在本地 SQLite 数据库文件中（`instance/ledger.db`）。

### Q: 如何迁移到其他电脑？
A: 复制整个项目文件夹，包括 `instance/ledger.db` 文件即可。

## ⚠️ 安全注意事项

1. **修改默认密钥**：务必修改 `.env` 中的 `SECRET_KEY`
2. **本地使用**：建议仅在本地或受信任的网络中使用
3. **定期备份**：定期备份数据库文件
4. **强密码**：使用强密码保护账户
5. **系统更新**：保持Python和依赖包为最新版本

更多安全相关信息请查看 [SECURITY.md](docs/SECURITY.md)

## 📄 许可证

本项目基于 MIT 许可证开源。详见 [LICENSE](LICENSE) 文件。

MIT License 允许：
- ✅ 商业使用
- ✅ 修改代码
- ✅ 分发使用
- ✅ 私人使用

## 🌟 致谢

感谢以下开源项目：
- [Flask](https://flask.palletsprojects.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Flask-Login](https://flask-login.readthedocs.io/)
- [bcrypt](https://github.com/pyca/bcrypt/)

---


### 版本标签管理

```bash
# 创建版本标签
git tag -a v1.0.0 -m "首个正式版本发布"

# 查看标签
git tag

# 推送标签到远程
git push origin v1.0.0
# 推送所有标签
git push origin --tags
```

### 常用Git命令

```bash
# 日常开发流程
git checkout -b feature/new-feature     # 创建功能分支
git add .                               # 添加更改
git commit -m "feat: 添加新功能"         # 提交
git push origin feature/new-feature     # 推送分支

# 同步主分支
git checkout develop
git pull origin develop
git merge feature/new-feature

# 发布版本
git checkout main
git merge develop
git tag -a v1.1.0 -m "版本1.1.0"
git push origin main --tags
```