import importlib.util
import sys


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


def test_env_sets_default_port(monkeypatch):
    manage = load_manage()
    monkeypatch.setenv("LLM_ROUTER_ENV", "test")
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["manage.py", "check"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "check"]
    assert manage.os.environ["LLM_ROUTER_ENV"] == "test"
    assert manage.os.environ["DB_PORT"] == "5432"


def test_explicit_db_port_is_preserved(monkeypatch):
    manage = load_manage()
    monkeypatch.setenv("LLM_ROUTER_ENV", "test")
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setattr(sys, "argv", ["manage.py", "prod", "check"])

    manage.configure_database_environment()

    assert sys.argv == ["manage.py", "check"]
    assert manage.os.environ["LLM_ROUTER_ENV"] == "prod"
    assert manage.os.environ["DB_PORT"] == "15432"
