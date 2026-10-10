"""Immutable, bounded preregistration; does not enqueue or execute experiments."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictFloat
from app.backtesting.strategies import strategy_registry
from app.services.research_experiments import preview
from .analysis import digest


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Budget(Strict):
    max_llm_spend_usd: float | None = Field(default=None, ge=0, le=10000)
    max_trial_runs: int = Field(default=80, ge=0, le=600, strict=True)
    max_trial_minutes: int = Field(default=60, ge=1, le=1440, strict=True)
    max_llm_calls: int = Field(default=12, ge=0, le=120, strict=True)
    max_hypotheses: int = Field(default=12, ge=1, le=100, strict=True)
    max_variants_per_hypothesis: int = Field(default=9, ge=1, le=25, strict=True)
    max_total_variants: int = Field(default=60, ge=1, le=500, strict=True)


class Axis(Strict):
    parameter: str = Field(min_length=1, max_length=120)
    mode: Literal["explicit"] = "explicit"
    values: list[StrictInt | StrictFloat] = Field(min_length=1, max_length=25)


class Hypothesis(Strict):
    request_key: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=4000)
    feature: str = Field(min_length=1, max_length=1000)
    discovery_dataset_ids: list[str] = Field(min_length=1, max_length=20)
    expected_result: str = Field(min_length=1, max_length=4000)
    falsification: str = Field(min_length=1, max_length=4000)
    researcher_reasoning: str = Field(min_length=1, max_length=4000)
    devils_advocate_objections: str = Field(min_length=1, max_length=12000)
    axes: list[Axis] = Field(min_length=1, max_length=2)


class HypothesisRepository:
    def __init__(self, database):
        self.database = database
        with database.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS agent_hypotheses(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, request_key TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(project_id,request_key))")

    def list(self, project_id):
        with self.database.connect() as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT document FROM agent_hypotheses WHERE project_id=? ORDER BY rowid", (project_id,))]

    def register(self, project_id, payload, *, committee_review_id=None, loop_id=None):
        from .repository import ResearchRepository
        ResearchRepository(self.database)
        proposal = Hypothesis.model_validate(payload).model_dump()
        proposal_hash = digest(proposal)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if loop_id:
                from .loop import require_active
                require_active(connection, project_id, loop_id)
            prior = connection.execute("SELECT document FROM agent_hypotheses WHERE project_id=? AND request_key=?", (project_id, proposal['request_key'])).fetchone()
            if prior:
                document = json.loads(prior[0])
                if document['proposal_hash'] != proposal_hash:
                    raise ValueError("Request key already belongs to a different hypothesis")
                return document
            row = connection.execute("SELECT document FROM agent_projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                raise ValueError("Unknown project")
            project = json.loads(row[0])
            if project['state'] != 'BASELINE_ANALYSIS' or not project.get('baseline_run_id'):
                raise ValueError("Inspect a baseline in an active project before preregistration")
            if strategy_registry.provenance(project['strategy_key']) != project['strategy_provenance']:
                raise ValueError("Strategy source changed; create a new lineage project")
            run = connection.execute("SELECT config_json,result_json FROM backtest_runs WHERE id=?", (project['baseline_run_id'],)).fetchone()
            if not run:
                raise ValueError("Frozen baseline was deleted")
            base = json.loads(run[0]); result = json.loads(run[1])
            source = result.get('strategy', {}).get('implementation')
            if source != project['strategy_provenance']:
                raise ValueError("Baseline source identity does not match the project; queue a verified baseline in a new project")
            fingerprint = base.get('market_data_fingerprint') or result.get('data', {}).get('fingerprint')
            if not fingerprint:
                raise ValueError("Baseline has no complete data fingerprint; preregistration requires a verified baseline")
            datasets = [json.loads(r[0]) for r in connection.execute("SELECT document FROM agent_datasets")]
            owned = {d['id']: d for d in datasets if d['project_id'] == project_id}
            for identifier in proposal['discovery_dataset_ids']:
                if identifier not in owned or owned[identifier]['state'] not in {'DEVELOPMENT', 'INSPECTED', 'INSPECTED_VALIDATION'}:
                    raise ValueError("Discovery evidence must be declared inspected/development data, never a locked holdout")
            scope = {'symbols': base['symbols'], 'start': base['start_date'], 'end': base['end_date']}
            if any(ResearchRepository.overlap(scope, d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):
                raise ValueError("Holdout firewall blocked preregistration")
            if not any(d['state'] in {'DEVELOPMENT','INSPECTED'} and set(scope['symbols']) <= set(d['symbols']) and d['start'] <= scope['start'] and scope['end'] <= d['end'] for d in owned.values()):
                raise ValueError("Experiments must remain on development data")
            plan = preview(base, proposal['axes'])
            budget = Budget.model_validate(project.get('research_budget', {})).model_dump()
            existing = [json.loads(r[0]) for r in connection.execute("SELECT document FROM agent_hypotheses WHERE project_id=?", (project_id,))]
            if len(existing) >= budget['max_hypotheses'] or plan['job_count'] > budget['max_variants_per_hypothesis'] or sum(h['plan']['job_count'] for h in existing) + plan['job_count'] > budget['max_total_variants']:
                raise ValueError("Research preregistration budget exhausted; no new hypothesis was stored")
            document = {**proposal, 'id': str(uuid4()), 'project_id': project_id, 'status': 'PREREGISTERED',
                        'created_at': datetime.now(timezone.utc).isoformat(), 'proposal_hash': proposal_hash,
                        'parent_run_id': project['baseline_run_id'], 'parent_source': source,
                        'parent_concepts': result.get('strategy', {}).get('concepts', {}), 'base_config': base,
                        'base_config_hash': digest(base), 'data_fingerprint': fingerprint, 'plan': plan,
                        'loop_id':loop_id, 'authorship': 'committee_loop_authorized' if loop_id else 'committee_user_approved' if committee_review_id else 'user', 'committee_review_id': committee_review_id, 'execution_enabled': False}
            connection.execute("INSERT INTO agent_hypotheses VALUES (?,?,?,?)", (document['id'], project_id, proposal['request_key'], json.dumps(document, allow_nan=False)))
            connection.execute("INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)", (project_id, 'hypothesis_preregistered', json.dumps({'hypothesis_id': document['id'], 'variants': plan['job_count']})))
        return document
