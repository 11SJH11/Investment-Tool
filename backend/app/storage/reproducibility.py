"""Recorded reproducibility manifests. No environment variables, credentials or host paths."""
import json
import platform
from importlib.metadata import version, PackageNotFoundError
from app.research_agent.analysis import digest


def environment_snapshot():
    packages={}
    for package in ('pandas','numpy','pydantic','duckdb'):
        try:packages[package]=version(package)
        except PackageNotFoundError:packages[package]=None
    return {'python':platform.python_version(),'implementation':platform.python_implementation(),
            'system':platform.system(),'machine':platform.machine(),'packages':packages,
            'scope':'Installed package versions observed at execution; not a lockfile, executable image or complete dependency archive.'}


def export_manifest(database,run_id):
    with database.connect() as c:
        row=c.execute('SELECT config_json,result_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
    if not row:raise ValueError('Saved run was not found')
    config,result=map(json.loads,row)
    keys=('strategy_key','symbols','start_date','end_date','primary_timeframe','additional_timeframes','session','strategy_params',
          'starting_balance','sizing_mode','risk_value','commission_per_order','slippage_bps','spread_bps','max_leverage',
          'max_open_positions','same_bar_policy','entry_windows','trading_weekdays','allow_overnight','force_close_time',
          'max_trades_per_day','max_daily_loss_r','max_consecutive_losses','cooldown_minutes')
    configuration={k:config[k] for k in keys if k in config}
    strategy=result.get('strategy',{});archive=strategy.get('source_archive',{})
    if archive.get('status')=='archived':
        from .strategy_source_archive import export_run
        export_run(database,run_id)  # Verify stored bytes; never use current source.
    data=result.get('data',{})
    fingerprint=config.get('market_data_fingerprint') or data.get('fingerprint')
    missing=[]
    if archive.get('status')!='archived':missing.append('Recorded strategy source bundle')
    if not fingerprint:missing.append('Full market-data fingerprint')
    if not result.get('execution_environment'):missing.append('Execution-time environment record')
    missing.extend(['Historical bar archive','Complete engine/concept/dependency source and executable environment'])
    document={'format':'ledger_reproducibility_manifest_v1','run_id':run_id,'configuration':configuration,
              'configuration_sha256':digest(configuration),'strategy_implementation':strategy.get('implementation'),
              'strategy_source_archive':archive or None,'concepts':strategy.get('concepts',{}),
              'market_data_fingerprint':fingerprint,'execution_environment':result.get('execution_environment'),
              'results_sha256':digest({'trades':result.get('trades',[]),'metrics':result.get('metrics'),'equity_curve':result.get('equity_curve')}),
              'missing_artifacts':missing,'replayable_archive':False,
              'limitations':['Manifest and hashes identify evidence; they do not contain bars or guarantee exact reruns.',
                             'Only recorded environment/source information is used. Legacy omissions remain unavailable.',
                             'Configuration includes strategy parameters. Review authored parameters and source exports before sharing. No environment variables or broker credentials are collected.']}
    return {**document,'manifest_sha256':digest(document)}
