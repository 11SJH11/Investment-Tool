"""Causal, indicator-registry-backed presentation. Never reruns a saved strategy."""
from math import isfinite
import pandas as pd
from app.indicators import indicator_registry
from app.backtesting.context import completion_indexes
from app.backtesting.review_contracts import LEGACY


def reconstruct(frames, trade, config, declaration, *, timeframe="1m"):
    params=config.get("strategy_params",{})
    meta=trade.get("metadata") or {}
    series=[];warnings=[]
    for item in declaration.get("series",[]):
        try:
            tf=item.get("timeframe",timeframe)
            frame=frames[tf].sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
            indicator=indicator_registry.create(item["indicator"])
            if not indicator.spec.causal:
                raise ValueError("Indicator is not declared causal")
            options={key:params[value["parameter"]] if isinstance(value,dict) and "parameter" in value else value for key,value in item.get("params",{}).items()}
            values=indicator.calculate(frame,**options)
            if isinstance(values,pd.DataFrame):
                values=values[item["column"]]
            availability=completion_indexes({tf:frame})[tf]
            points=[]
            for i,value in enumerate(values):
                if pd.isna(value) or not isfinite(float(value)):continue
                stamp=pd.Timestamp(frame.iloc[i]["timestamp"])
                if item.get("session_reset"):
                    day=stamp.tz_convert("America/New_York").date()
                    first=pd.Timestamp(frame.iloc[0]["timestamp"]).tz_convert("America/New_York")
                    if day==first.date() and first.hour*60+first.minute>570:continue
                points.append({"timestamp":stamp.isoformat(),"available_at":availability[i].isoformat(),"value":float(value)})
            output={"id":item["id"],"label":item.get("label",indicator.spec.name),"indicator":item["indicator"],"timeframe":tf,"overlay":indicator.spec.overlay,"provenance":"reconstructed","role":item.get("role","strategy_evidence"),"points":points}
            series.append(output)
            bps=float(params.get(item.get("distance_bps_param"),0) or 0)
            if bps>0:
                for sign,label in [(1,"upper"),(-1,"lower")]:
                    series.append({**output,"id":f"{item['id']}_{label}","label":f"{output['label']} {sign*bps:+g} bps","points":[{**p,"value":p["value"]*(1+sign*bps/10000)} for p in points]})
        except (KeyError,ValueError,TypeError,IndexError,ImportError) as exc:
            warnings.append(f"{item.get('label',item.get('id','Indicator'))}: unavailable ({exc})")
    frame=frames.get(timeframe,pd.DataFrame(columns=["timestamp"]))
    if "timestamp" not in frame:frame=pd.DataFrame(columns=["timestamp"])
    frame=frame.sort_values("timestamp").reset_index(drop=True)
    evidence={"entry":[],"exit":[]};highlights=[]
    def field(group,label,value,provenance="recorded",status=None):
        evidence[group].append({"label":label,"value":value,"provenance":provenance if value is not None else "not_recorded","status":status})
    for group in ['entry','exit']:
        stored=meta.get(f"review_{group}",{})
        fill=pd.Timestamp(trade[f"{group}_time"])
        stamp=stored.get("signal_time")
        confirmation=declaration.get("confirmation",{})
        # Only a declared next-open confirmation model permits legacy inference.
        allowed=bool(confirmation) and (group=='entry' or trade.get('exit_reason')==confirmation.get('exit_reason'))
        prior=frame[pd.to_datetime(frame.timestamp,utc=True)<fill] if len(frame) else frame
        if stamp is None and allowed and len(prior):
            stamp=completion_indexes({timeframe:prior.tail(1)})[timeframe][0].isoformat()
        field(group,'Signal time',stamp,'recorded' if stored.get('signal_time') else 'reconstructed')
        field(group,'Fill time',trade[f'{group}_time']);field(group,'Fill price',trade.get(f'{group}_price'))
        field(group,'Signal close',stored.get('signal_close'))
        for label,value in stored.get('indicators',{}).items():field(group,label+' at signal (recorded)',value)
        if stamp and allowed:
            required=int(params.get(confirmation.get(f'{group}_param'),meta.get('confirmation_bars',1)))
            field(group,'Required confirmation bars',required)
            base=next((s for s in series if s['id']==confirmation.get('series')),None)
            if base and len(frame):
                cutoff=pd.Timestamp(stamp)
                completed=frame.loc[completion_indexes({timeframe:frame})[timeframe]<=cutoff]
                points={pd.Timestamp(p['timestamp']):p for p in base['points'] if pd.Timestamp(p['available_at'])<=cutoff}
                selected=completed.tail(required)
                side=trade.get('direction');want_above=(side=='long')==(group=='entry')
                valid=len(selected)==required
                for row in selected.itertuples():
                    point=points.get(pd.Timestamp(row.timestamp))
                    valid=valid and point is not None and (float(row.close)>point['value'] if want_above else float(row.close)<point['value'])
                field(group,'Confirmation observed',stored.get('confirmation_observed',meta.get('confirmation_count') if group=='entry' else None))
                field(group,'Reconstructed confirmation',required if valid else None,'reconstructed','PASS' if valid else 'UNAVAILABLE / MISMATCH')
                if valid:highlights.extend({'timestamp':str(row.timestamp),'kind':group,'provenance':'reconstructed'} for row in selected.itertuples())
                if len(selected):
                    point=points.get(pd.Timestamp(selected.iloc[-1].timestamp))
                    if point:
                        field(group,base['label']+' at signal',point['value'],'reconstructed')
                        if group=='entry':
                            distance=abs(float(selected.iloc[-1].close)-point['value'])/point['value']*10000
                            field(group,'Distance (bps)',distance,'reconstructed')
                            definition=next((item for item in declaration.get('series',[]) if item.get('id')==base['id']),{})
                            limit=params.get(definition.get('distance_bps_param'))
                            field(group,'Maximum distance (bps)',limit,status='OFF' if not limit else 'PASS' if distance<=float(limit) else 'FAIL')
    for key in declaration.get('entry_fields',[]):field('entry',key.replace('_',' '),meta.get(key))
    for key in ['direction','entry_confirmation_bars','exit_confirmation_bars','trend_timeframe','trend_ema_length']:
        if key in params:field('entry','Configured '+key.replace('_',' '),params[key])
    for key in ['entry_windows','max_trades_per_day','cooldown_minutes']:
        field('entry',key.replace('_',' '),config.get(key))
    field('exit','Exit reason',trade.get('exit_reason'));field('exit','Net P&L',trade.get('net_pnl'));field('exit','Realised R',trade.get('r_multiple'))
    field('exit','Duration (minutes)',(pd.Timestamp(trade['exit_time'])-pd.Timestamp(trade['entry_time'])).total_seconds()/60)
    levels=[]
    for item in declaration.get("levels",[]):
        value=meta.get(item.get("metadata_key")) if "metadata_key" in item else params.get(item.get("parameter"))
        if isinstance(value,(int,float)) and isfinite(value):levels.append({"label":item.get("label",item.get("metadata_key",item.get("parameter"))),"value":value,"provenance":"recorded"})
    return {"series":series,"levels":levels,"evidence":evidence,"highlights":highlights,"warnings":warnings}


def review_trade(service,run_id,index,before=50,after=20,extended=False):
    saved=service.runs.get_section(run_id,'summary')
    # Extract only the requested immutable trade; do not transfer every trade.
    with service.runs.database.connect() as conn:
        row=conn.execute("SELECT json_extract(result_json, ?) AS trade FROM backtest_runs WHERE id=?",(f'$.trades[{int(index)}]',run_id)).fetchone()
    import json
    if row is None or row['trade'] is None:raise ValueError('Trade not found')
    trade=json.loads(row['trade']);config=saved['config'];result=saved['result']
    timeframe=result.get('primary_timeframe','1m');session=result.get('session','regular')
    meta=trade.get('metadata') or {}
    symbol=meta.get('source_contract') or meta.get('executed_contract') or trade['symbol']
    chart_warning=None
    try:
        bars=service.audit_bars(symbol=symbol,timeframe=timeframe,session=session,entry=pd.Timestamp(trade['entry_time']).to_pydatetime(),exit=pd.Timestamp(trade['exit_time']).to_pydatetime(),before_bars=before,after_bars=after)
    except Exception as exc:
        bars={'bars':[],'symbol':symbol,'timeframe':timeframe,'session':session}
        chart_warning=f'Historical candles unavailable ({type(exc).__name__}); recorded trade facts remain available.'
    declaration=result.get('strategy',{}).get('review_config') or LEGACY.get(result.get('strategy',{}).get('key'),{})
    from copy import deepcopy
    declaration=deepcopy(declaration)
    available_extended=any(s.get('extended_history') for s in declaration.get('series',[]))
    if not extended:declaration['series']=[s for s in declaration.get('series',[]) if not s.get('extended_history')]
    frames={timeframe:pd.DataFrame(bars['bars'])};warnings=[]
    if len(frames[timeframe]):
        start=pd.Timestamp(frames[timeframe].iloc[0].timestamp);end=pd.Timestamp(frames[timeframe].iloc[-1].timestamp)
        for tf in {s.get('timeframe',timeframe) for s in declaration.get('series',[])}:
            try:
                warm=start.tz_convert('America/New_York').normalize().tz_convert('UTC')
                # Session VWAP must start from session open; other declarations get bounded warmup.
                history_days=0
                for item in declaration.get('series',[]):
                    if item.get('timeframe',timeframe)!=tf:continue
                    days=item.get('history_days',0 if item.get('session_reset') else 400 if tf=='1d' else 10)
                    if isinstance(days,dict):days=days.get('values',{}).get(config.get('strategy_params',{}).get(days['parameter']),75)
                    history_days=max(history_days,min(365,int(days)))
                warm-=pd.Timedelta(days=history_days)
                loaded=service.audit_bars(symbol=symbol,timeframe=tf,session=session,start=warm.to_pydatetime(),end=(end+pd.Timedelta(days=1)).to_pydatetime())
                frames[tf]=pd.DataFrame(loaded['bars'])
            except Exception as exc:
                warnings.append(f'Historical {tf} indicator data unavailable ({type(exc).__name__}).')
    review=reconstruct(frames,trade,config,declaration,timeframe=timeframe)
    if chart_warning:review['warnings'].append(chart_warning)
    review['warnings']+=warnings+['Reconstructed from currently available historical bars. Original bar/provider revision identity is not guaranteed; recorded evidence takes precedence.']
    if not declaration.get("series") and not declaration.get("entry_fields"):review['warnings'].append('This strategy has no review declarations. Recorded trade facts remain available.')
    review['extended_available']=available_extended
    if len(bars['bars']):
        first=pd.Timestamp(bars['bars'][0]['timestamp']);last=pd.Timestamp(bars['bars'][-1]['timestamp'])
        for series in review['series']:
            previous=[p for p in series['points'] if pd.Timestamp(p['timestamp'])<first]
            series['points']=previous[-1:]+[p for p in series['points'] if first<=pd.Timestamp(p['timestamp'])<=last]
    review['warnings'].append('Recorded HTF evidence takes precedence. Extended reconstruction uses the current canonical strategy math; source versions, initial history seeds and incomplete sessions may differ from old runs.')
    return {**bars,'review':review,'trade':trade,'config':config}
