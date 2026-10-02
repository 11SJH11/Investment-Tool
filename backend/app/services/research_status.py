"""Compact read-only polling projections. Saved run snapshots stay unchanged."""
import json
import math


def cell_metrics(metrics, rows):
    mfe=[];mae=[];stops=targets=0
    finite=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    for row in rows:
        for values,candidates in ((mfe,row[:2]),(mae,row[2:4])):
            value=next((v for v in candidates if finite(v)),None)
            if value is not None: values.append(value)
        reason=row[4] or ''
        stops += 'stop' in reason
        targets += 'target' in reason or 'take_profit' in reason
    return {**metrics,'average_mfe':sum(mfe)/len(mfe) if mfe else None,
            'average_mae':sum(mae)/len(mae) if mae else None,'mfe_n':len(mfe),'mae_n':len(mae),
            'stop_pct':100*stops/len(rows) if rows else None,'target_pct':100*targets/len(rows) if rows else None}


def experiment_status(database, group):
    with database.connect() as db:
        row=db.execute("""SELECT json_extract(document,'$.status') AS status,
            json_extract(document,'$.cells') AS cells,json_extract(document,'$.error') AS error
            FROM research_experiments WHERE experiment_group=?""",(group,)).fetchone()
        if row is None: return None
        runs=db.execute("""SELECT id,json_extract(result_json,'$.metrics') AS metrics,
            (SELECT json_group_array(json_array(
                CASE WHEN json_type(value,'$.metadata')='object' THEN value -> '$.metadata.mfe_r' ELSE value -> '$.source_metadata.mfe_r' END,
                CASE WHEN json_type(value,'$.metadata')='object' THEN value -> '$.metadata.mfe_r_lower_bound' ELSE value -> '$.source_metadata.mfe_r_lower_bound' END,
                CASE WHEN json_type(value,'$.metadata')='object' THEN value -> '$.metadata.mae_r' ELSE value -> '$.source_metadata.mae_r' END,
                CASE WHEN json_type(value,'$.metadata')='object' THEN value -> '$.metadata.mae_r_lower_bound' ELSE value -> '$.source_metadata.mae_r_lower_bound' END,
                value -> '$.exit_reason')) FROM json_each(result_json,'$.trades')) AS diagnostics
            FROM backtest_runs WHERE experiment_group=?""",(group,)).fetchall()
    cells=json.loads(row['cells'] or '[]');by_id={run['id']:run for run in runs}
    for cell in cells:
        run=by_id.get(cell.get('run_id'))
        if run: cell['metrics']=cell_metrics(json.loads(run['metrics'] or '{}'),json.loads(run['diagnostics'] or '[]'))
    return {'experiment_group':group,'status':row['status'],'cells':cells,'error':row['error']}


def research_history(database):
    with database.connect() as db:
        rows=db.execute("""SELECT experiment_group,
            json_extract(document,'$.experiment_id') AS experiment_id,
            json_extract(document,'$.name') AS name,
            json_extract(document,'$.experiment_type') AS experiment_type,
            json_extract(document,'$.test_role') AS test_role,
            json_extract(document,'$.status') AS status,
            json_array_length(document,'$.cells') AS total,
            (SELECT count(*) FROM json_each(document,'$.cells') WHERE json_extract(value,'$.status')='completed') AS completed,
            json_object('strategy_key',json_extract(document,'$.base_configuration.strategy_key'),
                        'symbols',json_extract(document,'$.base_configuration.symbols'),
                        'start_date',json_extract(document,'$.base_configuration.start_date'),
                        'end_date',json_extract(document,'$.base_configuration.end_date')) AS base_configuration
            FROM research_experiments ORDER BY updated_at DESC LIMIT 100""").fetchall()
    return [{**dict(row),'base_configuration':json.loads(row['base_configuration'])} for row in rows]
