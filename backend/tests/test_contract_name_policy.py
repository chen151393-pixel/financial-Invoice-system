"""文件名缩减保留地区和商号，不强行截字或产生空名称。"""

import pytest
from backend.modules.task.policy.contract_name_policy import supplier_filename_name


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("东莞市创远机械有限公司", "东莞创远"),
        ("杭州燊兴包装材料有限责任公司", "杭州燊兴"),
        ("浙江洪皓工贸有限公司", "浙江洪皓"),
        ("环鑫智能有限公司", "环鑫智能"),
        ("河南省莆阳炫彩", "河南省莆阳炫彩"),
        ("柯梦", "柯梦"),
        ("机械有限公司", "机械"),
        ("有限公司", "有限公司"),
        ("", ""),
    ],
)
def test_supplier_filename_keeps_meaningful_name(full, short):
    assert supplier_filename_name(full) == short
