import importlib.util
import os
from pathlib import Path

from app.core.config import Settings


def test_launcher_drops_inherited_credentials_and_forces_local_state(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'environ', os.environ.copy())
    spec = importlib.util.spec_from_file_location(
        'isolated_launcher', Path(__file__).resolve().parents[2] / 'tools/run_isolated.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    (tmp_path / 'backend').mkdir()
    state = tmp_path / '.ledger-runtime'
    state.mkdir()
    (state / 'providers.env').write_text('LEDGER_DATA_DIR=ignored\nMT5_SERVER=isolated-fixture\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('MT5_PASSWORD', 'inherited-fixture-secret')
    monkeypatch.setenv('LEDGER_DATA_DIR', 'original-checkout')
    launcher.configure()
    settings = Settings(_env_file=None)
    assert settings.data_dir == state / 'data'
    assert not settings.mt5_password
    assert settings.mt5_server == 'isolated-fixture'
    assert settings.cors_origins == ['http://localhost:5174', 'http://127.0.0.1:5174']


def test_default_cors_preserves_standard_frontend(monkeypatch):
    monkeypatch.delenv('LEDGER_CORS_ORIGINS', raising=False)
    assert Settings(_env_file=None).cors_origins == ['http://localhost:5173', 'http://127.0.0.1:5173']
