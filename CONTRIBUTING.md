# 贡献指南

感谢您考虑为本项目做出贡献！以下是参与项目开发的一些规范和指南。

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [测试规范](#测试规范)
- [文档规范](#文档规范)
- [Issue规范](#issue规范)
- [Pull Request规范](#pull-request规范)
- [版本发布流程](#版本发布流程)

## 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们作为贡献者和维护者承诺，无论年龄、体型、残疾、种族、性别认同和表达、经验水平、国籍、个人外貌、种族、宗教或性取向如何，参与我们的项目和社区都不会受到骚扰。

### 我们的标准

有助于创造积极环境的行为包括：
- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同情

不可接受的行为包括：
- 使用性相关的语言或图像，以及不受欢迎的性关注或进步
- 恶意评论、侮辱/贬损性评论以及人身或政治攻击
- 公开或私下骚扰
- 未经明确许可发布他人的私人信息
- 在专业环境中可能被合理地认为不适当的其他行为

## 如何贡献

### 贡献类型

您可以通过以下方式贡献：

1. **报告Bug**：创建Issue描述问题
2. **建议新功能**：创建Issue描述功能需求
3. **改进文档**：修复错别字、改进说明
4. **提交代码**：修复Bug或实现新功能
5. **代码审查**：审查Pull Request
6. **测试**：编写测试用例或进行手动测试
7. **回答问题**：在Issues中帮助其他开发者

### 开始贡献

1. Fork本仓库
2. 克隆你的Fork到本地
3. 添加上游仓库
4. 创建功能分支
5. 进行开发
6. 提交Pull Request

```bash
# 1. Fork仓库（在GitHub网页操作）

# 2. 克隆到本地
git clone https://github.com/YOUR_USERNAME/personal-ledger.git
cd personal-ledger

# 3. 添加上游仓库
git remote add upstream https://github.com/ORIGINAL_OWNER/personal-ledger.git

# 4. 创建功能分支
git checkout -b feature/your-feature-name

# 5. 进行开发...

# 6. 同步上游更新
git fetch upstream
git rebase upstream/main
```

## 开发流程

### 环境搭建

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. 配置环境
cp .env.example .env
# 编辑.env文件，设置SECRET_KEY

# 4. 初始化数据库
python scripts/init_db.py

# 5. 运行应用
python run.py
```

### 开发工作流

1. **分配任务**：在Issue中认领要做的任务
2. **创建分支**：从`develop`分支创建功能分支
3. **编写代码**：遵循代码规范编写代码
4. **编写测试**：为新功能编写测试用例
5. **本地测试**：确保所有测试通过
6. **提交代码**：使用约定式提交格式
7. **推送分支**：推送到你的Fork仓库
8. **创建PR**：在GitHub创建Pull Request
9. **代码审查**：根据审查意见修改代码
10. **合并代码**：审查通过后合并到主分支

### 分支命名规范

```
feature/xxx        # 新功能
bugfix/xxx         # Bug修复
hotfix/xxx         # 紧急修复
release/xxx        # 发布分支
docs/xxx           # 文档更新
refactor/xxx       # 代码重构
test/xxx           # 测试相关
chore/xxx          # 构建/工具相关
```

示例：
- `feature/add-export-function`
- `bugfix/fix-login-error`
- `docs/update-installation-guide`
- `refactor/improve-database-queries`

## 代码规范

### Python代码风格

遵循PEP 8规范，具体要求：

#### 命名规范

```python
# 模块名：小写+下划线
import my_module

# 类名：大驼峰
class UserAccount:
    pass

# 函数名：小写+下划线
def calculate_total():
    pass

# 变量名：小写+下划线
user_count = 0

# 常量：大写+下划线
MAX_RETRY_COUNT = 3

# 私有属性/方法：前置单下划线
_internal_method()
_private_variable = None
```

#### 代码格式

```python
# 好的示例

from sqlalchemy import select
from app import db

def process_records(user_id, start_date=None, end_date=None):
    """
    处理用户记录
    
    Args:
        user_id: 用户ID
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
    
    Returns:
        list: 处理后的记录列表
    """
    if not user_id:
        raise ValueError("user_id不能为空")
    
    stmt = select(Record).where(Record.user_id == user_id)
    
    if start_date:
        stmt = stmt.where(Record.date >= start_date)
    if end_date:
        stmt = stmt.where(Record.date <= end_date)
    
    return db.session.scalars(stmt).all()

# 不好的示例
def p(u, s=None, e=None):
    r = Record.query.filter_by(user_id=u)
    if s: r = r.filter(Record.date >= s)
    if e: r = r.filter(Record.date <= e)
    return r.all()
```

#### 导入顺序

```python
# 1. 标准库
import os
import sys
from datetime import datetime

# 2. 第三方库
from flask import Flask, request
from sqlalchemy import desc

# 3. 本地模块
from app.models import User, Record
from app.utils.validators import validate_amount
```

### 注释规范

```python
# 模块级文档字符串
"""
用户认证模块

提供用户注册、登录、登出等功能。
"""

# 类文档字符串
class RecordService:
    """
    记录服务类
    
    处理账本记录的增删改查操作。
    
    Attributes:
        user: 当前用户对象
    """
    
    def add_record(self, data):
        """
        添加新记录
        
        Args:
            data (dict): 记录数据，包含：
                - amount (float): 金额
                - category (str): 分类
                - record_type (str): 类型
            
        Returns:
            Record: 创建的记录对象
            
        Raises:
            ValueError: 数据验证失败
        """
        pass
```

### 安全规范

```python
# 1. 永远不要信任用户输入
def process_user_input(user_input):
    # 清理HTML标签
    clean_input = bleach.clean(user_input, tags=[])
    # 验证长度
    if len(clean_input) > 200:
        raise ValueError("输入过长")
    return clean_input

# 2. 使用参数化查询（SQLAlchemy自动处理）
# 好的做法
select(Record).where(Record.user_id == user_id)

# 3. 密码必须哈希
from bcrypt import hashpw, gensalt
password_hash = hashpw(password.encode(), gensalt(12))

# 4. 敏感信息不记录日志
# 错误
logger.info(f"用户登录：用户名={username}, 密码={password}")

# 正确
logger.info(f"用户登录：用户名={username}")
```

## 提交规范

### 约定式提交格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type类型

- `feat`: 新功能（feature）
- `fix`: 修复Bug
- `docs`: 文档更新
- `style`: 代码格式调整（不影响功能）
- `refactor`: 代码重构
- `perf`: 性能优化
- `test`: 测试相关
- `build`: 构建系统或外部依赖
- `ci`: CI配置文件和脚本
- `chore`: 其他不修改src或test的修改
- `revert`: 回退之前的提交

### 提交示例

```
feat(records): 添加记录导出为CSV功能

实现将用户记录导出为CSV文件的功能：
- 支持按日期范围筛选
- 支持选择导出字段
- 添加导出进度提示

Closes #123

fix(auth): 修复连续登录失败不锁定账户的问题

- 添加登录失败次数记录
- 5次失败后锁定账户30分钟
- 解锁后重置失败计数器

Fixes #456

docs(readme): 更新安装说明和常见问题

增加了Docker部署说明，更新了Python版本要求。

refactor(database): 优化记录查询性能

- 添加复合索引(id, user_id, date)
- 移除不必要的JOIN查询
- 使用批量插入代替循环插入

性能提升约40%

test(models): 添加用户模型的单元测试

测试覆盖：
- 用户创建
- 密码验证
- 唯一性约束
- 关系查询

覆盖率提升至85%
```

### 提交频率

- 保持提交粒度适中
- 一个提交做一件事
- 避免大量文件的一次性提交
- WIP（Work In Progress）提交可以后续squash

## 测试规范

### 测试结构

```
tests/
├── conftest.py              # 全局测试配置
├── test_models.py           # 模型测试
├── test_auth.py             # 认证测试
├── test_records.py          # 记录测试
├── test_validators.py       # 验证器测试
└── test_security.py         # 安全测试
```

### 测试编写

```python
import pytest
from app.models import User, Record
from app import db

class TestUserModel:
    """用户模型测试"""
    
    def test_create_user(self, app):
        """测试创建用户"""
        with app.app_context():
            user = User(username='testuser')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
            
            assert user.id is not None
            assert user.username == 'testuser'
            assert user.password_hash != 'password123'
    
    def test_password_verification(self, app):
        """测试密码验证"""
        with app.app_context():
            user = User(username='testuser')
            user.set_password('correct_password')
            
            assert user.check_password('correct_password')
            assert not user.check_password('wrong_password')
    
    def test_unique_username(self, app):
        """测试用户名唯一性"""
        with app.app_context():
            user1 = User(username='testuser')
            user1.set_password('password123')
            db.session.add(user1)
            db.session.commit()
            
            user2 = User(username='testuser')
            user2.set_password('password456')
            db.session.add(user2)
            
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

class TestRecordModel:
    """记录模型测试"""
    
    def test_create_record(self, app, test_user):
        """测试创建记录"""
        with app.app_context():
            record = Record(
                user_id=test_user.id,
                amount=100.50,
                category='餐饮',
                description='午餐',
                record_type='expense'
            )
            db.session.add(record)
            db.session.commit()
            
            assert record.id is not None
            assert record.amount == 100.50
    
    def test_amount_validation(self):
        """测试金额验证"""
        assert Record.validate_amount(100.50) == 100.50
        assert Record.validate_amount('100.50') == 100.50
        assert Record.validate_amount(0) == False
        assert Record.validate_amount(-10) == False
        assert Record.validate_amount(100000000) == False
        assert Record.validate_amount('abc') == False
```

### 测试运行

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_models.py

# 运行特定测试类
pytest tests/test_models.py::TestUserModel

# 运行特定测试方法
pytest tests/test_models.py::TestUserModel::test_create_user

# 带详细输出
pytest -v

# 带覆盖率报告
pytest --cov=app --cov-report=html

# 失败时停止
pytest -x

# 只运行上次失败的测试
pytest --lf
```

### 测试覆盖率要求

- 新增代码覆盖率不低于80%
- 核心业务逻辑覆盖率不低于90%
- 关键安全功能覆盖率100%

## 文档规范

### 文档更新

修改代码时，同步更新相关文档：

- API变更 → 更新API.md
- 数据库变更 → 更新DATABASE.md
- 新功能 → 更新README.md
- 安全相关 → 更新SECURITY.md

### 文档风格

- 使用清晰简洁的语言
- 包含代码示例
- 使用Markdown格式
- 添加适当的标题层级

```markdown
# 一级标题：模块名

## 二级标题：功能名

### 三级标题：子功能

- 使用无序列表
1. 使用有序列表

**粗体**强调重要信息
`代码`标记变量或文件名

```python
# 代码块指定语言
print("Hello")
```
```

## Issue规范

### Bug报告模板

```markdown
### 描述
清晰描述bug的表现

### 复现步骤
1. 打开页面 '...'
2. 点击按钮 '....'
3. 输入数据 '....'
4. 出现错误

### 期望行为
描述期望的正确行为

### 截图
如可能，添加截图

### 环境信息
- 操作系统: [例如 Windows 10]
- Python版本: [例如 3.9.0]
- 浏览器: [例如 Chrome 120]
- 项目版本: [例如 v1.0.0]

### 附加信息
其他相关信息
```

### 功能请求模板

```markdown
### 功能描述
清晰描述想要的功能

### 使用场景
描述这个功能的使用场景

### 建议方案
如果有实现想法，描述建议的实现方案

### 替代方案
描述考虑过的替代方案

### 附加信息
原型图、参考链接等
```

## Pull Request规范

### PR标题格式

```
<type>(<scope>): <description>
```

### PR描述模板

```markdown
## 变更类型
- [ ] Bug修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 代码重构
- [ ] 其他

## 变更描述
简要描述此PR的变更内容

## 相关Issue
Closes #123
Related to #456

## 测试
- [ ] 添加了单元测试
- [ ] 所有测试通过
- [ ] 覆盖率不低于变更前

## 截图
如适用，添加截图

## 检查清单
- [ ] 代码符合项目规范
- [ ] 添加了必要的注释
- [ ] 更新了相关文档
- [ ] 新依赖已添加到requirements.txt
- [ ] 本地测试通过
- [ ] 无安全漏洞

## 附加说明
其他需要说明的事项
```

### 代码审查流程

1. **自动检查**：GitHub Actions自动运行测试
2. **人工审查**：至少需要一位维护者审查
3. **修改建议**：审查者提出修改建议
4. **代码修改**：提交者根据建议修改代码
5. **批准合并**：审查通过后合并

### 代码审查要点

- 功能是否符合需求
- 代码是否清晰易读
- 是否有充分的错误处理
- 是否有安全漏洞
- 测试是否充分
- 文档是否更新
- 性能是否有影响

## 版本发布流程

### 版本号规范

遵循语义化版本（Semantic Versioning）：

```
主版本号.次版本号.修订号

例如：1.2.3
- 主版本号(1)：不兼容的API修改
- 次版本号(2)：向下兼容的功能新增
- 修订号(3)：向下兼容的问题修正
```

### 发布步骤

1. 从develop创建release分支
2. 更新版本号和CHANGELOG
3. 最终测试
4. 合并到main分支
5. 创建版本标签
6. 发布到GitHub Releases

```bash
# 1. 创建release分支
git checkout develop
git checkout -b release/1.1.0

# 2. 更新版本号
# 编辑setup.py中的version
# 更新CHANGELOG.md

# 3. 提交更新
git add .
git commit -m "chore(release): 准备发布v1.1.0"

# 4. 合并到main
git checkout main
git merge release/1.1.0

# 5. 创建标签
git tag -a v1.1.0 -m "v1.1.0 - 添加数据导出功能"

# 6. 推送
git push origin main --tags

# 7. 合并回develop
git checkout develop
git merge release/1.1.0
git push origin develop
```

### 发布检查清单

- [ ] 所有测试通过
- [ ] 安全扫描通过
- [ ] 文档已更新
- [ ] CHANGELOG已更新
- [ ] 版本号已更新
- [ ] 创建GitHub Release
- [ ] 通知相关开发者

## 获取帮助

- **问题讨论**：[GitHub Discussions](https://github.com/ORIGINAL_OWNER/personal-ledger/discussions)
- **开发问题**：[GitHub Issues](https://github.com/ORIGINAL_OWNER/personal-ledger/issues)
- **邮件联系**：maintainer@example.com

## 致谢

再次感谢您的贡献！每个贡献者都让这个项目变得更好。

---

<div align="center">
  <p>Happy Coding! 🎉</p>
</div>