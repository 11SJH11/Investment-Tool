"""Preparation boundary for closed-trade CSV adapters; no writes or fill reconstruction.

Broker-specific formats must supply tested mappings before being advertised as supported.
"""
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone

REQUIRED={'external_id','ticker','direction','opened_at','closed_at','entry_price','exit_price','quantity','position_currency'}
OPTIONAL={'fees','pnl_amount'}


def preview_statement(text, mapping, account_scope):
    if len(text)>2_000_000:raise ValueError('Statement exceeds 2 MB')
    if not account_scope.strip():raise ValueError('A stable statement account scope is required')
    if not REQUIRED <= mapping.keys() or set(mapping)-REQUIRED-OPTIONAL:raise ValueError('Map all required closed-trade fields')
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('CSV needs unique column headers')
    if not set(mapping.values())<=set(reader.fieldnames):raise ValueError('Mapped CSV column is missing')
    items=[];errors=[];identities=set()
    for line,row in enumerate(reader,2):
        if line>5001:raise ValueError('Statement exceeds 5000 rows')
        try:
            item={key:str(row.get(column) or '').strip() for key,column in mapping.items()}
            if not item['external_id'] or not item['ticker']:raise ValueError('Trade ID and ticker are required')
            if item['direction'].lower() not in {'long','short'}:raise ValueError('Direction must explicitly be long or short')
            item['direction']=item['direction'].lower();item['ticker']=item['ticker'].upper()
            for key in ('opened_at','closed_at'):
                stamp=datetime.fromisoformat(item[key].replace('Z','+00:00'))
                if stamp.tzinfo is None:raise ValueError('Timestamps need an explicit UTC offset')
                item[key]=stamp.astimezone(timezone.utc).isoformat()
            if item['closed_at']<item['opened_at']:raise ValueError('Exit precedes entry')
            for key in ('entry_price','exit_price','quantity','fees','pnl_amount'):
                if key not in item:continue
                try:value=float(item[key])
                except ValueError:raise ValueError('Numeric fields require plain decimal numbers') from None
                if not math.isfinite(value) or (key in {'entry_price','exit_price','quantity'} and value<=0) or (key=='fees' and value<0):raise ValueError('Invalid numeric field')
                item[key]=value
            currency=item['position_currency'].upper()
            if len(currency)!=3 or not currency.isalpha():raise ValueError('Currency must be a three-letter code')
            item['position_currency']=currency
            identity=hashlib.sha256(json.dumps([account_scope.strip(),item['external_id']],ensure_ascii=True).encode()).hexdigest()
            if identity in identities:raise ValueError('Duplicate trade ID in this statement')
            identities.add(identity)
            item.update(source='broker_statement',external_provider='statement',external_id=identity,source_metadata={'format':'mapped_closed_trade_csv_v1'})
            items.append(item)
        except (ValueError,TypeError):
            # Do not echo arbitrary statement cells, account identifiers or exception values.
            errors.append({'line':line,'message':'Invalid closed-trade row: check required values, explicit offsets, numbers and unique IDs.'})
    return {'items':items,'errors':errors,'valid':not errors,'preview_only':True,'notice':'No records written. This boundary accepts completed trade rows, not raw fills. Broker-specific adapters and import confirmation are not enabled.'}
