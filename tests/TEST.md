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

# 运行带测试用例的测试
pytest tests/ -v --tb=short

```