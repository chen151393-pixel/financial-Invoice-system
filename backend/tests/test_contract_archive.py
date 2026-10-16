"""共享盘命名、不可覆盖与路径边界。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.integrations.contract_archive import ContractArchive, contract_filename

PDF = b"%PDF-1.4\nexample\n%%EOF"


def test_china_download_date_filename_and_same_content_reuse(tmp_path):
    archive = ContractArchive(tmp_path)
    at = datetime(2026, 8, 16, 16, 30, tzinfo=UTC).timestamp()
    path, name = archive.save("YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", at, PDF)
    assert name == "YE-HH20260422-X1004-1浙江洪皓工贸有限公司.pdf"
    target = Path(path)
    assert target.parent.name == "2026年8月17日"
    original = target.stat().st_mtime_ns
    assert archive.save("YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", at, PDF)[0] == path
    assert target.stat().st_mtime_ns == original
    archive.save("SECOND", "供应商", at + 60, PDF)
    assert len(list(tmp_path.iterdir())) == 1
    assert not list(tmp_path.rglob("*.tmp"))


def test_same_name_different_content_never_overwrites(tmp_path):
    archive = ContractArchive(tmp_path)
    path, _ = archive.save("SUB-1", "供应商", 0, PDF)
    with pytest.raises(ApiError) as error:
        archive.save("SUB-1", "供应商", 0, PDF + b"different")
    assert error.value.status == 409
    assert Path(path).read_bytes() == PDF


def test_missing_share_is_not_created_and_bad_filename_cannot_escape(tmp_path):
    root = tmp_path / "offline-share"
    with pytest.raises(ApiError) as error:
        ContractArchive(root).save("SUB-1", "供应商", 0, PDF)
    assert error.value.status == 503 and not root.exists()
    assert contract_filename("../SUB:1", "公司/部门*") == ".._SUB_1公司_部门_.pdf"
    with pytest.raises(ApiError):
        contract_filename("", "公司")
