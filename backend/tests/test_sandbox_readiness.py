"""Deterministic Docker diagnostics and exact-image recovery contracts."""
import json
import subprocess
from unittest.mock import Mock

import pytest

from app.research_agent import sandbox


@pytest.fixture
def docker():
    runtime = sandbox.Docker('readiness-unit')
    yield runtime
    runtime.close()


@pytest.mark.parametrize('stderr,code', [
    (b'No such image: ledger-research-sandbox:v1', 'SANDBOX_IMAGE_MISSING'),
    (b'Cannot connect to the Docker daemon', 'DOCKER_DAEMON_UNAVAILABLE'),
    (b'unknown failure secret-token', 'DOCKER_COMMAND_FAILED'),
])
def test_command_diagnostics_do_not_echo_sensitive_stderr(docker, monkeypatch, stderr, code):
    monkeypatch.setattr(subprocess, 'run', Mock(return_value=subprocess.CompletedProcess([], 1, b'', stderr)))
    with pytest.raises(sandbox.SandboxError, match=code) as caught:
        docker.call('image', 'inspect', 'private-reference')
    assert caught.value.diagnostics['operation'] == 'image inspect'
    assert caught.value.diagnostics['exit_code'] == 1
    assert len(caught.value.diagnostics['stderr_sha256']) == 64
    assert 'secret-token' not in str(caught.value)


@pytest.mark.parametrize('error,code', [
    (subprocess.TimeoutExpired('docker', 1), 'DOCKER_COMMAND_TIMEOUT'),
    (FileNotFoundError(), 'DOCKER_UNAVAILABLE'),
])
def test_command_deadline_and_missing_executable(docker, monkeypatch, error, code):
    monkeypatch.setattr(subprocess, 'run', Mock(side_effect=error))
    with pytest.raises(sandbox.SandboxError, match=code):
        docker.call('info')


@pytest.mark.parametrize('tags,expected', [(['ledger-research-sandbox:v1'], True), (['other:v1'], False)])
def test_tag_resolution_requires_verified_exact_identity(docker, tags, expected):
    identifier = 'sha256:' + 'a' * 64
    docker.call = Mock(side_effect=[sandbox.SandboxError('SANDBOX_IMAGE_MISSING'), identifier,
                                   json.dumps([{'Id': identifier, 'RepoTags': tags}])])
    if expected:
        assert docker.inspect_image('ledger-research-sandbox:v1')['Id'] == identifier
    else:
        with pytest.raises(sandbox.SandboxError, match='IDENTITY_MISMATCH'):
            docker.inspect_image('ledger-research-sandbox:v1')
    assert docker.call.call_args_list[1].args[-1] == 'reference=ledger-research-sandbox:v1'


@pytest.mark.parametrize('ids', ['', 'sha256:' + 'a'*64 + '\nsha256:' + 'b'*64, 'not-an-id'])
def test_missing_or_ambiguous_image_fails_closed(docker, ids):
    docker.call = Mock(side_effect=[sandbox.SandboxError('SANDBOX_IMAGE_MISSING'), ids])
    with pytest.raises(sandbox.SandboxError, match='IMAGE_MISSING'):
        docker.inspect_image('ledger-research-sandbox:v1')


@pytest.mark.parametrize('fail', [False, True])
def test_readiness_runs_worker_and_always_cleans_up(docker, monkeypatch, fail):
    docker.image = Mock(return_value='sha256:'+'a'*64)
    session = Mock()
    monkeypatch.setattr(sandbox, 'Session', Mock(return_value=session))
    remote = Mock()
    if fail:
        remote.reset.side_effect = sandbox.SandboxError('STRATEGY_VALIDATION_OR_EXECUTION_FAILED')
    factory = Mock(return_value=remote)
    monkeypatch.setattr(sandbox, 'RemoteStrategy', factory)
    if fail:
        with pytest.raises(sandbox.SandboxError):
            docker.preflight()
    else:
        assert docker.preflight()['cleanup_completed'] is True
    remote.reset.assert_called_once()
    session.close.assert_called_once()
