"""环境文件只加载 .env，保留部署注入及测试显式配置。"""

from backend.core import config


def test_only_dotenv_is_read(monkeypatch, tmp_path):
    calls = []

    def read(path, *, interpolate):
        calls.append(path)
        assert path == tmp_path / ".env"
        assert interpolate is False
        return {"PORT": "4567", "ADMIN_USERNAME": "dotenv-user"}

    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "dotenv_values", read)
    monkeypatch.setattr(config.os, "environ", {"PORT": "4568"})
    settings = config.load_settings()
    assert settings.port == 4568 and settings.admin_user == "dotenv-user"
    assert calls == [tmp_path / ".env"]
    assert config.load_settings({"PORT": "4569"}).port == 4569
    assert calls == [tmp_path / ".env"]
