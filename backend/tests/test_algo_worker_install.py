import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

spec=importlib.util.spec_from_file_location('algo_install',Path(__file__).resolve().parents[2]/'deploy/install_algo_worker.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


@pytest.fixture
def setup(tmp_path):
    root=tmp_path/'repo';module=root/'backend/app/forward/demo_worker.py'
    module.parent.mkdir(parents=True);module.write_text("if __name__ == '__main__': pass")
    python=root/'backend/.venv/bin/python';python.parent.mkdir(parents=True);python.touch()
    config=tmp_path/'worker.json';config.write_text('{}');config.chmod(0o600)
    state=tmp_path/'state'
    return root,config,state


def test_plan_has_no_side_effects_or_service_dependencies(setup):
    root,config,state=setup
    name,unit,result=installer.plan(root,'demo','app.forward.demo_worker',config,state)
    assert name=='ledger-algo-demo.service' and result==state and not state.exists()
    assert 'Restart=no' in unit and 'ProtectSystem=strict' in unit
    assert 'ReadWritePaths='+installer.quote(state) in unit
    assert all(s not in unit for s in ['telegram','18766','.mt5-live','PartOf=','Requires='])


@pytest.mark.parametrize('bad',['../../telegram','demo.service','LIVE/bridge'])
def test_unit_name_injection_rejected(setup,bad):
    root,config,state=setup
    with pytest.raises(ValueError):installer.plan(root,bad,'app.forward.demo_worker',config,state)


def test_never_adopts_production_state_or_env(setup):
    root,config,state=setup
    state.mkdir();(state/'ledger.db').write_bytes(b'preserve')
    with pytest.raises(ValueError,match='adopt'):installer.plan(root,'demo','app.forward.demo_worker',config,state)
    assert (state/'ledger.db').read_bytes()==b'preserve'
    with pytest.raises(ValueError,match='outside'):installer.plan(root,'demo','app.forward.demo_worker',config,root/'backend/data')
    env=config.with_name('.env');env.touch()
    with pytest.raises(ValueError,match='.env'):installer.plan(root,'demo','app.forward.demo_worker',env,root.parent/'other')


def test_install_only_reloads_manager_and_is_idempotent(setup,tmp_path):
    root,config,state=setup
    service,unit,state=installer.plan(root,'demo','app.forward.demo_worker',config,state)
    commands=[]
    def run(command,**kwargs):
        commands.append(command);return NS(returncode=0,stdout='inactive\n')
    path=installer.install(tmp_path/'home',service,unit,state,'demo',run=run)
    installer.install(tmp_path/'home',service,unit,state,'demo',run=run)
    assert path.read_text()==unit
    assert commands==[['systemctl','--user','show',service,'--property=ActiveState','--value'],['systemctl','--user','daemon-reload'],['systemctl','--user','show',service,'--property=ActiveState','--value']]
    installer.plan(root,'demo','app.forward.demo_worker',config,state)


def test_active_worker_cannot_be_replaced_or_stopped_by_installer(setup,tmp_path):
    root,config,state=setup
    service,unit,state=installer.plan(root,'demo','app.forward.demo_worker',config,state)
    with pytest.raises(ValueError,match='stopped'):
        installer.install(tmp_path/'home',service,unit,state,'demo',replace=True,run=lambda *a,**kw:NS(returncode=0,stdout='active\n'))
    assert not state.exists() and not (tmp_path/'home').exists()


def test_replacement_is_explicit_owned_and_backed_up(tmp_path):
    path=tmp_path/'unit';path.write_text('unrelated service')
    with pytest.raises(ValueError):installer.publish(path,installer.MARKER+'new',replace=True)
    assert path.read_text()=='unrelated service'
    path.write_text(installer.MARKER+'old')
    with pytest.raises(ValueError):installer.publish(path,installer.MARKER+'new')
    installer.publish(path,installer.MARKER+'new',replace=True)
    assert next(tmp_path.glob('unit.backup-*')).read_text()==installer.MARKER+'old'


def test_non_cli_module_is_not_presented_as_deployable(setup):
    root,config,state=setup
    (root/'backend/app/forward/demo_worker.py').write_text('class DiagnosticWorker: pass')
    with pytest.raises(ValueError,match='not deployable'):
        installer.plan(root,'demo','app.forward.demo_worker',config,state)
