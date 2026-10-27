"""共享盘命名、不可覆盖与路径边界：月份/CD号_真实报关单号/子采购单号_供应商_真实报关单号.pdf。"""

from datetime import datetime
from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.integrations.contract_archive import ContractArchive, contract_filename, declaration_folder

PDF = b"%PDF-1.4\nexample\n%%EOF"
# NS 创建时间按 UTC 保存；中国时间 2026-09-01 00:30，归档月份 2026年09月
DECLARATION = {
    "record_no": "CD000870",
    "declaration_no": "REAL870",
    "created_at": datetime(2026, 8, 31, 16, 30),
}


def test_month_declaration_folder_contract_name_and_same_content_reuse(tmp_path):
    archive = ContractArchive(tmp_path)
    path, name = archive.save(DECLARATION, "YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", PDF)
    assert name == "YE-HH20260422-X1004-1_浙江洪皓工贸有限公司_REAL870.pdf"
    target = Path(path)
    assert target.parent.name == "CD000870_REAL870" and target.parent.parent.name == "2026年09月"
    original = target.stat().st_mtime_ns
    assert archive.save(DECLARATION, "YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", PDF)[0] == path
    assert target.stat().st_mtime_ns == original
    second = Path(archive.save(DECLARATION, "SECOND", "供应商", PDF)[0])
    assert second.parent == target.parent  # 同一报关单的合同放在同一文件夹
    assert [p.name for p in tmp_path.iterdir()] == ["2026年09月"]
    assert not list(tmp_path.rglob("*.tmp"))


def test_same_name_different_content_never_overwrites(tmp_path):
    archive = ContractArchive(tmp_path)
    path, _ = archive.save(DECLARATION, "SUB-1", "供应商", PDF)
    with pytest.raises(ApiError) as error:
        archive.save(DECLARATION, "SUB-1", "供应商", PDF + b"different")
    assert error.value.status == 409
    assert Path(path).read_bytes() == PDF


def test_missing_share_is_not_created_and_bad_names_cannot_escape(tmp_path):
    root = tmp_path / "offline-share"
    with pytest.raises(ApiError) as error:
        ContractArchive(root).save(DECLARATION, "SUB-1", "供应商", PDF)
    assert error.value.status == 503 and not root.exists()
    assert contract_filename("../SUB:1", "公司/部门*", "REAL:870") == ".._SUB_1_公司_部门__REAL_870.pdf"
    assert declaration_folder("../CD:1", "..\\REAL") == ".._CD_1_.._REAL"
    with pytest.raises(ApiError):
        contract_filename("", "公司", "REAL870")


@pytest.mark.parametrize(
    ("field", "reason"),
    [("created_at", "NS 创建时间"), ("declaration_no", "真实报关单号"), ("record_no", "CD 编号")],
)
def test_missing_declaration_head_is_refused_without_guessing(tmp_path, field, reason):
    archive = ContractArchive(tmp_path)
    with pytest.raises(ApiError, match=reason) as error:
        archive.save({**DECLARATION, field: None}, "SUB-1", "供应商", PDF)
    assert error.value.status == 409
    assert not list(tmp_path.iterdir())
