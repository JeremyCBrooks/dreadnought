"""Tests for web/main.py server config env var reading."""


def test_port_defaults_to_8000(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    from web.main import _server_config

    _, port, _ = _server_config()
    assert port == 8000


def test_port_reads_from_env(monkeypatch):
    monkeypatch.setenv("PORT", "9000")
    from web.main import _server_config

    _, port, _ = _server_config()
    assert port == 9000


def test_port_is_int(monkeypatch):
    monkeypatch.setenv("PORT", "7777")
    from web.main import _server_config

    _, port, _ = _server_config()
    assert isinstance(port, int)


def test_log_level_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    from web.main import _server_config

    _, _, log_level = _server_config()
    assert log_level == "info"


def test_log_level_reads_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    from web.main import _server_config

    _, _, log_level = _server_config()
    assert log_level == "debug"


def test_host_is_always_all_interfaces(monkeypatch):
    from web.main import _server_config

    host, _, _ = _server_config()
    assert host == "0.0.0.0"
