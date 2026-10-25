import importlib.util
import json
from pathlib import Path
import pytest
import subprocess
import sys

spec=importlib.util.spec_from_file_location('live_deploy',Path(__file__).resolve().parents[2]/'deploy/setup_mt5_live_bridge.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)


def test_private_atomic_configuration_idempotence_backup_and_refusal(tmp_path):
    path=tmp_path/'private/config.json'
    assert deploy.private_write(path,'one')
    assert not deploy.private_write(path,'one')
    with pytest.raises(RuntimeError):deploy.private_write(path,'two')
    assert path.read_text()=='one'
    deploy.private_write(path,'two',replace=True)
    assert path.read_text()=='two'
    assert next(path.parent.glob('*.backup-*')).read_text()=='one'


def test_profile_merge_never_duplicates_or_replaces_existing():
    prior=[{'id':'other','provider':'oanda','credentials':{'token':'fixture-private'}}]
    live={'id':'mt5-live','provider':'mt5','environment':'live','credentials':{'bridge_url':'http://127.0.0.1:18766'}}
    merged=deploy.merge_profile(prior,live)
    assert prior==merged[:1] and len(prior)==1
    assert deploy.merge_profile(merged,live)==merged
    with pytest.raises(RuntimeError):deploy.merge_profile(merged,{**live,'environment':'demo'})


def test_live_service_never_uses_demo_prefix_or_boot_without_graphical_session(tmp_path):
    unit=deploy.unit(tmp_path/'config',tmp_path/'.mt5-live','/usr/bin/wine')
    assert 'WantedBy=graphical-session.target' in unit
    assert 'StartLimitBurst=3' in unit and 'WINEPREFIX='+str(tmp_path/'.mt5-live') in unit
    assert 'telegram' not in unit and 'ledger-mt5-bridge.service' not in unit


def test_prerequisite_selection_cannot_escape_live_prefix(tmp_path):
    prefix=tmp_path/'live';prefix.mkdir()
    outside=tmp_path/'terminal64.exe';outside.write_text('fixture')
    with pytest.raises(RuntimeError):deploy.choose(prefix,'terminal64.exe',str(outside))


def test_system_dropin_publishes_complete_file_without_overwriting(tmp_path):
    source=tmp_path/'source';source.write_text('[Service]\nEnvironment=SAFE=1\n')
    target=tmp_path/'system/override.conf'
    command=[sys.executable,'-c',deploy.INSTALL_DROPIN_CODE,str(source),str(target)]
    assert subprocess.run(command,capture_output=True).returncode==0
    assert target.read_bytes()==source.read_bytes()
    source.write_text('replacement')
    assert subprocess.run(command,capture_output=True).returncode!=0
    assert target.read_text()=='[Service]\nEnvironment=SAFE=1\n'
    assert not list(target.parent.glob('.ledger-*'))
