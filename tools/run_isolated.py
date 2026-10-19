"""Run this worktree on port 8012 with worktree-local mutable state."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))


def configure():
    from app.core.config import Settings
    from dotenv import load_dotenv
    # Do not inherit the stable checkout's provider credentials/data settings.
    for name, field in Settings.model_fields.items():
        alias = field.validation_alias
        if isinstance(alias, str):
            os.environ.pop(alias, None)
        os.environ.pop(name, None)
        os.environ.pop(name.upper(), None)
    state = ROOT/'.ledger-runtime'
    state.mkdir(exist_ok=True)
    load_dotenv(state/'providers.env', override=True)
    os.environ['LEDGER_DATA_DIR'] = str(state/'data')
    os.environ['LEDGER_CORS_ORIGINS'] = '["http://localhost:5174","http://127.0.0.1:5174"]'
    os.chdir(ROOT/'backend')


if __name__ == '__main__':
    configure()
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=8012)
