"""Offline comparison of licensed/user-supplied continuous CSV exports."""
import pandas as pd


def compare_exports(ledger, reference):
    frames=[]
    for name,source in [('ledger',ledger),('reference',reference)]:
        frame=source.copy()
        required={'timestamp','open','high','low','close','volume'}
        if not required.issubset(frame):
            raise ValueError(f'{name} export requires timestamp and OHLCV columns')
        # Reject timezone-less exports rather than silently shifting a market session.
        stamps=frame.timestamp.map(pd.Timestamp)
        if any(t.tzinfo is None for t in stamps):
            raise ValueError('Export timestamps must include timezone offsets')
        frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
        if frame.timestamp.duplicated().any():raise ValueError('Duplicate export timestamps')
        for col in ['open','high','low','close','volume']:
            frame[col]=pd.to_numeric(frame[col],errors='raise')
            if not frame[col].map(lambda v:pd.notna(v) and float('-inf')<v<float('inf')).all():
                raise ValueError('Export OHLCV must be finite')
        frames.append(frame.set_index('timestamp'))
    a,b=frames;common=a.index.intersection(b.index)
    result=dict(ledger_bars=len(a),reference_bars=len(b),matched_timestamps=len(common),
        missing_from_ledger=[str(t) for t in b.index.difference(a.index)],
        missing_from_reference=[str(t) for t in a.index.difference(b.index)],
        max_absolute_difference={c:float((a.loc[common,c]-b.loc[common,c]).abs().max()) if len(common) else None for c in ['open','high','low','close','volume']},
        source_contract_mismatches=None,rolls={})
    if 'source_contract' in a and 'source_contract' in b:
        result['source_contract_mismatches']=int((a.loc[common,'source_contract']!=b.loc[common,'source_contract']).sum())
    for name,frame in zip(['ledger','reference'],frames):
        if 'source_contract' in frame:
            ordered=frame.sort_index();changed=ordered.source_contract.ne(ordered.source_contract.shift())
            result['rolls'][name]=[dict(timestamp=str(t),source_contract=r.source_contract) for t,r in ordered.loc[changed].iloc[1:].iterrows()]
    return result
