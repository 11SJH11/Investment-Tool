"""Static selection of archived strategy dependencies. Never imports source."""
import ast
import base64
from .input_limits import ARCHIVED_SOURCE_BYTES

PREFIX='app.backtesting.strategies.'
CANONICAL={'base','registry','strategy_registry'}
MAX_SOURCE_BYTES=ARCHIVED_SOURCE_BYTES


def imports(source):
    names=set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node,ast.Import):
            names.update(a.name[len(PREFIX):] for a in node.names if a.name.startswith(PREFIX))
        elif isinstance(node,ast.ImportFrom):
            module=node.module or ''
            if node.level:
                if node.level!=1:raise ValueError('Archived strategy dependency escapes its package')
                names.update([module] if module else [a.name for a in node.names])
            elif module.startswith(PREFIX):names.add(module[len(PREFIX):])
            elif module==PREFIX.rstrip('.'):
                names.update(a.name for a in node.names if a.name!='strategy_registry')
    return names-CANONICAL


def archived_parent(database,run_id,provenance):
    from app.storage.strategy_source_archive import export_run
    bundle=export_run(database,run_id)
    if bundle['provenance']!=provenance:
        raise ValueError('Archived parent provenance differs from the frozen reference')
    selected={}
    def collect(filename):
        if filename in selected:return
        if filename not in bundle['files']:
            raise ValueError('Archived dependency is missing; current source is not a substitute: '+filename)
        raw=base64.b64decode(bundle['files'][filename],validate=True)
        selected[filename]=raw.decode('utf-8')
        if len(selected)>32 or sum(len(s.encode()) for s in selected.values())>MAX_SOURCE_BYTES:
            raise ValueError('Archived dependency bundle exceeds author input bound')
        for name in sorted(imports(selected[filename])):
            if '.' in name or name.startswith('__'):raise ValueError('Unsupported archived strategy dependency')
            collect(name+'.py')
    module=bundle['archive']['module'];collect(module)
    return dict(module=module,source=selected.pop(module),sha256=bundle['manifest'][module],
                dependencies=selected,dependency_manifest={n:bundle['manifest'][n] for n in selected},
                archive_sha256=bundle['archive']['sha256'],limitation=bundle['warning'])


def sandbox_modules(database,candidate,source):
    requested=imports(source)
    if not requested:return {}
    archive=archived_parent(database,candidate['run_id'],candidate['snapshot']['source'])
    modules={archive['module']:archive['source'],**archive['dependencies']}
    if any(name+'.py' not in modules for name in requested):
        raise ValueError('Generated source requests a strategy outside its frozen parent dependency bundle')
    return modules
