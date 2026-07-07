import pytest
from app import db
from app.models import (
    Category, User, CategoryType, BluecoinsCategoryMapping
)
from app.services.import_service import ImportService
from sqlalchemy import select


# ===============================================================
# 测试用 CSV
# ===============================================================

CATEGORIES_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","投资","基金收息","U45024",776.23,1,1,"联博美国债券","U45024","投资","基金收息","I"
2021,"支出","投资","基金涨跌","U44706",10.7,9,2,"首源全球基建","U44706","投资","基金涨跌","I"
2021,"支出","日常","交通","上班交通",776.23,50,3,"交通",,"日常","交通","E"
"""

EMPTY_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","日常","交通","上班交通",0,0,10,,,,,,
"""

DUPLICATE_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","日常","交通","交通1",0,0,20,"交通",,"日常","交通","E"
2022,"支出","日常","交通","交通2",0,0,21,"交通",,"日常","交通","E"
"""

INCOME_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"收入","职业","工资","月薪",50000,12,30,"工资",,"职业","主业","I"
"""

TRANSFER_CATEGORY_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"转账","转账","内部转账","账户转账",0,5,40,"账户转账",,"转账","内部转账","T"
"""

MIXED_CSV = """年份,类型,类别分组名称,类别,标题,总金额,总笔数,category_id,category_name,category_other_name,category_class,category_subclass,category_type
2021,"支出","投资","基金涨跌","U44564",3608.41,9,,,,,,,
2021,"支出","娱乐","购物","零食",-10,1,4,"日常杂货",,"购物","日常杂货","E"
2021,"支出","其它","其它","调整",-10.11,2,5,"对账调整",,"其它","对账调整","S"
2021,"支出","娱乐","购物","饮料",-18,1,4,"日常杂货",,"购物","日常杂货","E"
2021,"支出","娱乐","购物","运费加收",-20,1,6,"运费",,"购物","运费","E"
"""


# ===============================================================
# 测试类
# ===============================================================

class TestImportCategories:
    """分类导入测试"""

    def test_import_basic(self, app, test_user):
        """基本导入：3 个分类全部成功"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(CATEGORIES_CSV)

            assert result['success'] == 3
            assert result['skipped'] == 0
            assert result['failed'] == 0

    def test_import_creates_categories(self, app, test_user):
        """导入后分类属性正确"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(CATEGORIES_CSV)

            cat = db.session.scalars(
                select(Category).where(Category.category_name == '联博美国债券')
            ).first()
            assert cat is not None
            assert cat.category_type == CategoryType.INCOME
            assert cat.category_class == '投资'
            assert cat.category_subclass == '基金收息'

            cat2 = db.session.scalars(
                select(Category).where(Category.category_name == '交通')
            ).first()
            assert cat2 is not None
            assert cat2.category_type == CategoryType.EXPENSE
            assert cat2.category_class == '日常'

    def test_import_creates_mappings(self, app, test_user):
        """导入后创建 Bluecoins 映射"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(CATEGORIES_CSV)

            mapping = db.session.scalars(
                select(BluecoinsCategoryMapping).where(
                    BluecoinsCategoryMapping.bluecoins_group == '投资',
                    BluecoinsCategoryMapping.bluecoins_category == '基金收息',
                    BluecoinsCategoryMapping.bluecoins_title == 'U45024'
                )
            ).first()
            assert mapping is not None
            assert mapping.is_manual is False

    def test_import_skip_existing(self, app, test_user):
        """重复导入全部跳过"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service1 = ImportService(user)
            result1 = service1.import_categories_csv(CATEGORIES_CSV)
            assert result1['success'] == 3

            # 新建实例模拟重新导入
            service2 = ImportService(user)
            result2 = service2.import_categories_csv(CATEGORIES_CSV)
            assert result2['skipped'] == 3
            assert result2['success'] == 0

    def test_import_skip_empty_row(self, app, test_user):
        """跳过分类字段为空的行"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(EMPTY_CATEGORY_CSV)

            assert result['skipped'] == 1
            assert result['success'] == 0

    def test_import_skip_duplicate_combination(self, app, test_user):
        """完全重复组合跳过第二个"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(DUPLICATE_CATEGORY_CSV)

            assert result['success'] == 1
            assert result['skipped'] == 1

    def test_import_income_type(self, app, test_user):
        """导入收入类型分类"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(INCOME_CATEGORY_CSV)

            cat = db.session.scalars(
                select(Category).where(Category.category_name == '工资')
            ).first()
            assert cat is not None
            assert cat.category_type == CategoryType.INCOME

    def test_import_transfer_type(self, app, test_user):
        """导入转账类型分类"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(TRANSFER_CATEGORY_CSV)

            cat = db.session.scalars(
                select(Category).where(Category.category_name == '账户转账')
            ).first()
            assert cat is not None
            assert cat.category_type == CategoryType.TRANSFER

    def test_import_mixed(self, app, test_user):
        """混合导入：空行跳过、重复跳过、正确创建"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(MIXED_CSV)

            # 第1行空 → 跳过；第2行零食 → 成功；第3行调整 → 成功；
            # 第4行饮料 → 与零食重复，跳过；第5行运费 → 成功
            assert result['success'] == 3
            assert result['skipped'] == 2
            assert result['failed'] == 0

    def test_mixed_creates_correct_categories(self, app, test_user):
        """混合导入后数据库中有正确的分类"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(MIXED_CSV)

            # 日常杂货（零食和饮料合并为一条）
            cat1 = db.session.scalars(
                select(Category).where(Category.category_name == '日常杂货')
            ).first()
            assert cat1 is not None
            assert cat1.category_class == '购物'
            assert cat1.category_type == CategoryType.EXPENSE

            # 对账调整
            cat2 = db.session.scalars(
                select(Category).where(Category.category_name == '对账调整')
            ).first()
            assert cat2 is not None
            assert cat2.category_type == CategoryType.SPECIAL

            # 运费
            cat3 = db.session.scalars(
                select(Category).where(Category.category_name == '运费')
            ).first()
            assert cat3 is not None
            assert cat3.category_class == '购物'

    def test_bluecoins_mapping_no_owner_id(self, app, test_user):
        """分类映射不存储 owner_id"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            service.import_categories_csv(CATEGORIES_CSV)

            mapping = db.session.scalars(
                select(BluecoinsCategoryMapping).where(
                    BluecoinsCategoryMapping.bluecoins_group == '投资',
                    BluecoinsCategoryMapping.bluecoins_category == '基金收息'
                )
            ).first()
            assert mapping is not None
            assert not hasattr(mapping, 'owner_id')

    def test_import_result_details(self, app, test_user):
        """导入结果包含详细信息"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv(CATEGORIES_CSV)

            assert len(result['details']) == 3
            for detail in result['details']:
                assert detail['status'] == 'success'
                assert 'name' in detail
                assert 'category_name' in detail

    def test_import_empty_csv(self, app, test_user):
        """空 CSV 不报错"""
        with app.app_context():
            user = db.session.get(User, test_user)
            service = ImportService(user)
            result = service.import_categories_csv('')

            assert result['success'] == 0
            assert result['failed'] == 0
