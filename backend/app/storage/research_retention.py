"""Protect saved evidence referenced by durable research records from ordinary deletion."""
import json


class ResearchRunProtected(ValueError):
    pass


def require_deletable(connection, run_id):
    # Caller holds BEGIN IMMEDIATE through deletion, serializing with research writers.
    row=connection.execute('SELECT config_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
    if row is None:raise ValueError(f'Backtest run {run_id} was not found')
    config=json.loads(row[0])
    protected=any(config.get(key) for key in ('research_project_id','research_trial_id','research_validation_id'))
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ('agent_projects','agent_trials','agent_candidates','agent_validations','agent_concept_audits','agent_decisions'):
        if protected:break
        if table not in tables:continue
        # Fixed identifiers only; nested cell/lineage references are included without loading results.
        protected=connection.execute(
            f"SELECT 1 FROM {table} AS record, json_tree(record.document) AS field "
            "WHERE field.key IN ('run_id','parent_run_id','baseline_run_id','candidate_run_id') "
            "AND CAST(field.atom AS TEXT)=? LIMIT 1",(str(run_id),)).fetchone() is not None
        if table=='agent_projects' and not protected:
            protected=connection.execute(
                "SELECT 1 FROM agent_projects AS project, json_each(project.document,'$.analyses') AS analysis "
                "WHERE analysis.key=? LIMIT 1",(str(run_id),)).fetchone() is not None
    if protected:
        raise ResearchRunProtected('This run is retained as research evidence and cannot be deleted through Runs. Archiving a project does not remove its evidence.')
