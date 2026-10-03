"""Audit names from source, never read a developer's .env or credentials."""
import ast
from pathlib import Path


def test_safe_example_covers_actual_settings_and_has_no_credential_values():
    root=Path(__file__).resolve().parents[2]
    source=ast.parse((root/'backend/app/core/config.py').read_text(encoding='utf-8'))
    names=set()
    for node in ast.walk(source):
        if isinstance(node,ast.keyword) and node.arg=='validation_alias':
            names.add(ast.literal_eval(node.value))
    lines=(root/'.env.example').read_text(encoding='utf-8').splitlines()
    values=dict(line.split('=',1) for line in lines if line and not line.startswith('#'))
    assert names<=values.keys()
    assert set(values)-names=={'LEDGER_FRAME_CACHE_ENTRIES','LEDGER_FRAME_CACHE_MB','LEDGER_FRAME_CACHE_TTL','VITE_API_BASE_URL'}
    for name,value in values.items():
        if any(part in name for part in ('API_KEY','API_SECRET','ACCESS_TOKEN','PASSWORD','EMAIL','ACCOUNT_ID','LOGIN','CLIENT_SECRET','SECRET_KEY')):
            assert value==''
    assert values['TRADELOCKER_ENABLED']==values['MT5_ENABLED']=='false'
    assert values['BROKER_PROFILES_JSON']=='[]'
    assert '.env' in (root/'.gitignore').read_text(encoding='utf-8').splitlines()
