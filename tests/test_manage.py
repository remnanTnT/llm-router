import importlib.util
import sys

import pytest


ROOT = __file__.rsplit("/tests/", 1)[0]


def load_manage():
    spec = importlib.util.spec_from_file_location("manage", f"{ROOT}/manage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prod_selector_sets_default_port(monkeypatch):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "prod", "check"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "check"]
    assert manage.os.environ["LLM_ROUTER_ENV"] == "prod"
    assert manage.os.environ["DB_PORT"] == "5431"


def test_test_selector_sets_default_port(monkeypatch):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "test", "check"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "check"]
    assert manage.os.environ["LLM_ROUTER_ENV"] == "test"
    assert manage.os.environ["DB_PORT"] == "5432"


def test_explicit_db_port_is_preserved(monkeypatch):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setattr(sys, "argv", ["manage.py", "prod", "check"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "check"]
    assert manage.os.environ["LLM_ROUTER_ENV"] == "prod"
    assert manage.os.environ["DB_PORT"] == "15432"


def test_missing_selector_exits(monkeypatch, capsys):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "check"])

    with pytest.raises(SystemExit) as exc_info:
        manage.configure_database_environment()

    assert exc_info.value.code == 2
    assert "prod" in capsys.readouterr().err


def test_env_var_alone_is_not_accepted(monkeypatch):
    manage = load_manage()
    monkeypatch.setenv("LLM_ROUTER_ENV", "test")
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "check"])

    with pytest.raises(SystemExit):
        manage.configure_database_environment()


def test_no_args_is_allowed(monkeypatch):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py"]


def test_help_token_is_allowed(monkeypatch):
    manage = load_manage()
    monkeypatch.delenv("LLM_ROUTER_ENV", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "--help"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "--help"]
