from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_services
from app.api.research import router
from app.core.config import Settings
from app.services.container import build_services
from app.storage.research_experiment_repository import ResearchExperimentRepository


def test_research_items_through_real_container_preserve_identity_and_experiments(tmp_path):
    services = build_services(Settings(_env_file=None, LEDGER_DATA_DIR=tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_services] = lambda: services
    experiments = ResearchExperimentRepository(services.database)
    experiments.save({'experiment_group': 'fixture', 'cells': [], 'status': 'completed'})
    try:
        with TestClient(app) as client:
            payload = {'source': 'fixture', 'source_item_id': 'signal-1',
                       'instrument': 'spy', 'title': 'Original', 'metadata': {'note': 'kept'}}
            first = client.post('/research/items', json=payload)
            assert first.status_code == 200
            trade_id = first.json()['id']
            updated = client.post('/research/items', json={**payload, 'title': 'Updated'})
            assert updated.status_code == 200
            assert updated.json()['id'] == trade_id
            items = client.get('/research/items', params={'instrument': 'SPY', 'source': 'fixture'}).json()['items']
            assert len(items) == 1 and items[0]['title'] == 'Updated'
            assert items[0]['metadata'] == {'note': 'kept'}
            assert client.get('/research/items', params={'instrument': 'QQQ'}).json()['items'] == []
            assert client.delete(f'/research/items/{trade_id}').status_code == 200
            assert client.delete(f'/research/items/{trade_id}').status_code == 404
            assert client.get('/research/items').json()['items'] == []
            assert experiments.get('fixture')['status'] == 'completed'
    finally:
        services.close()


def test_manual_notes_without_external_ids_remain_distinct_and_survive_restart(tmp_path):
    settings = Settings(_env_file=None, LEDGER_DATA_DIR=tmp_path)
    services = build_services(settings)
    try:
        a = services.research.save_item({'title': 'First', 'instrument': 'spy'})
        b = services.research.save_item({'title': 'Second', 'instrument': 'spy'})
        assert a['id'] != b['id']
    finally:
        services.close()
    services = build_services(settings)
    try:
        assert {x['id'] for x in services.research.list_items(instrument='spy')} == {a['id'], b['id']}
    finally:
        services.close()
