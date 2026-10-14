from hashlib import sha256
import os
from pathlib import Path
import pytest
from tests.test_strategy_source_archive import repository, save
from app.research_agent.source_dependencies import archived_parent, sandbox_modules
from app.research_agent.input_limits import ARCHIVED_SOURCE_BYTES


def test_archive_transitive_dependencies_are_exact_inert_and_not_current_files(repository,tmp_path):
    marker=tmp_path/'not-executed'
    sources={'fixture.py':b'from .helper import Parent\n',
             'helper.py':f'from app.backtesting.strategies.leaf import VALUE\nopen({str(marker)!r},"w").write("bad")'.encode(),
             'leaf.py':b'VALUE=7', 'unrelated.py':b'raise RuntimeError()'}
    run=save(repository,sources)
    bundle=archived_parent(repository.database,run['id'],run['result']['strategy']['implementation'])
    assert set(bundle['dependencies'])=={'helper.py','leaf.py'}
    assert bundle['dependency_manifest']['leaf.py']==sha256(sources['leaf.py']).hexdigest()
    assert not marker.exists()
    candidate={'run_id':run['id'],'snapshot':{'source':run['result']['strategy']['implementation']}}
    assert set(sandbox_modules(repository.database,candidate,'from app.backtesting.strategies.fixture import Child'))=={'fixture.py','helper.py','leaf.py'}
    with pytest.raises(ValueError,match='outside its frozen parent'):
        sandbox_modules(repository.database,candidate,'from app.backtesting.strategies.unrelated import X')


@pytest.mark.parametrize('source,other,match',[
    (b'from .missing import X',{},'missing'),
    (b'from ..models import X',{},'escapes'),
    (b'from .helper import X',{'helper.py':b'#'+b'x'*ARCHIVED_SOURCE_BYTES},'bound'),
])
def test_missing_unsafe_or_oversize_dependencies_fail_without_substitution(repository,source,other,match):
    run=save(repository,{'fixture.py':source,**other})
    with pytest.raises(ValueError,match=match):archived_parent(repository.database,run['id'],run['result']['strategy']['implementation'])


def test_vwap_v5_real_archive_captures_inherited_v4_without_other_strategies(repository):
    from app.storage.strategy_source_archive import manifest_for
    root=Path(__file__).parents[1]/'app/backtesting/strategies'
    names=['vwap_trend_confirmation_quality_research_v5.py','vwap_trend_entry_exit_distance_research_v4.py']
    sources={n:(root/n).read_bytes() for n in names}
    manifest,identity=manifest_for(sources)
    provenance={'module':'app.backtesting.strategies.'+names[0][:-3],'source_sha256':manifest[names[0]],'registry_sha256':identity}
    run=repository.create(config={},result={'strategy':{'implementation':provenance}},strategy_sources=sources)
    bundle=archived_parent(repository.database,run['id'],provenance)
    assert set(bundle['dependencies'])=={names[1]}


def test_large_archived_bundle_is_exact_at_bound_and_rejects_one_more_byte(repository):
    parent=b'from .helper import X\n'
    helper=b'X=1\n#'+b'x'*(ARCHIVED_SOURCE_BYTES-len(parent)-5)
    assert len(parent)+len(helper)==ARCHIVED_SOURCE_BYTES
    run=save(repository,{'fixture.py':parent,'helper.py':helper})
    bundle=archived_parent(repository.database,run['id'],run['result']['strategy']['implementation'])
    assert bundle['dependencies']['helper.py'].encode()==helper
    too_large=save(repository,{'fixture.py':parent,'helper.py':helper+b'x'})
    with pytest.raises(ValueError,match='bound'):
        archived_parent(repository.database,too_large['id'],too_large['result']['strategy']['implementation'])


@pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER')!='1',reason='Opt-in archived dependency Docker acceptance')
def test_archived_parent_inheritance_runs_only_inside_docker(repository,tmp_path):
    from app.research_agent.sandbox import Docker,Session,RemoteStrategy
    from tests.test_research_sandbox_docker import context, SOURCE
    marker=tmp_path/'host-marker'
    parent=SOURCE.replace('research_child_fixture','archived_parent')+'\n#'+('x'*65000)
    sources={'fixture.py':parent.encode()}
    run=save(repository,sources)
    candidate={'run_id':run['id'],'snapshot':{'source':run['result']['strategy']['implementation']}}
    child='''from dataclasses import replace
from app.backtesting.strategies.fixture import Child as Parent
class Child(Parent):
    spec=replace(Parent.spec,key='research_child_inherited')
'''
    runtime=Docker('dependencies-'+str(tmp_path))
    try:
        with_session=Session(runtime,runtime.image(),seconds=30)
        try:
            remote=RemoteStrategy(with_session,child,'research_child_inherited',{},modules=sandbox_modules(repository.database,candidate,child))
            remote.reset()
            assert remote.on_bar(context()).stop_loss==98
            assert with_session.provenance['dependency_sha256']
            assert not marker.exists()
        finally:with_session.close()
    finally:runtime.cleanup();runtime.close()
