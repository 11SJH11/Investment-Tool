"""Automation is execution provenance, never inferred from broker/account names."""
def automation_fields(data):
    source=data.get('source','live_manual');meta=data.get('source_metadata') or {}
    if source=='backtest':automated,origin=True,'strategy'
    elif source in {'live_manual','paper_manual','replay'}:automated,origin=False,'manual'
    else:
        automated=data.get('is_automated')
        origin=data.get('execution_source') or 'imported'
        if automated not in (None,True,False,0,1):raise ValueError('Invalid automation provenance')
        if origin not in {'manual','strategy','agent','imported','unknown'}:raise ValueError('Invalid execution source')
        if origin in {'strategy','agent'}:automated=True
    return {'is_automated':automated,'execution_source':origin,
            'strategy_id':str(data.get('strategy_id') or meta.get('strategy_key') or ''),
            'strategy_name':str(data.get('strategy_name') or meta.get('strategy_name') or ''),
            'strategy_run_id':str(data.get('strategy_run_id') or meta.get('run_id') or '')}
