"""Explicit allowlisted build context. No repository, settings, database or secrets."""
from hashlib import sha256
from pathlib import Path
import json
import shutil

TAG = 'ledger-research-sandbox:v1'
FILES = ('backtesting/context.py','backtesting/models.py','backtesting/strategies/base.py',
         'research_agent/sandbox_wire.py','research_agent/sandbox_worker.py')
PACKAGES = ('indicators', 'market_concepts')
DOCKERFILE = '''ARG BASE
FROM ${BASE}
RUN pip install --no-cache-dir pandas==3.0.6 numpy==2.4.6 pydantic==2.12.5
COPY app /opt/ledger/app
WORKDIR /opt/ledger
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 HOME=/scratch
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "app.research_agent.sandbox_worker"]
'''
REGISTRY = '''class Registry:
    def register(self, cls): return cls
strategy_registry = Registry()
'''


def stage(destination):
    destination = Path(destination)
    if any(destination.iterdir()): raise ValueError('Build context must be an empty private directory')
    root = Path(__file__).resolve().parents[1]
    files = list(FILES)
    for package in PACKAGES:
        files.extend(str(p.relative_to(root)).replace('\\','/') for p in (root/package).glob('*.py'))
    for name in files:
        source = root/name
        if source.is_symlink(): raise ValueError('Symlinks forbidden in sandbox build context')
        target = destination/'app'/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source,target)
    for name in ('app/__init__.py','app/backtesting/__init__.py','app/research_agent/__init__.py'):
        (destination/name).write_text('',encoding='utf-8')
    (destination/'app/backtesting/strategies/__init__.py').write_text(REGISTRY,encoding='utf-8')
    (destination/'Dockerfile').write_text(DOCKERFILE,encoding='utf-8')
    manifest = {str(p.relative_to(destination)).replace('\\','/'):sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    return {'files': manifest, 'sha256': sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()}
