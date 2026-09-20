import pytest
from app.services.statement_import import preview_statement, REQUIRED

HEADER=','.join(sorted(REQUIRED))

def statement(**patch):
    values=dict(external_id='1',ticker='aapl',direction='long',opened_at='2026-01-01T10:00:00Z',closed_at='2026-01-01T11:00:00Z',entry_price='100',exit_price='102',quantity='2',position_currency='USD');values.update(patch)
    return HEADER+'\n'+','.join(values[k] for k in sorted(REQUIRED))

def test_preview_identity_is_stable_and_account_scoped():
    mapping={k:k for k in REQUIRED};text=statement()
    a=preview_statement(text,mapping,'account A');b=preview_statement(text,mapping,'account A');c=preview_statement(text,mapping,'account B')
    assert a==b and a['valid'] and a['preview_only']
    assert a['items'][0]['external_id']!=c['items'][0]['external_id']
    assert a['items'][0]['ticker']=='AAPL'
    assert 'account A' not in str(a)

@pytest.mark.parametrize('patch',[{'opened_at':'2026-01-01T10:00:00'},{'quantity':'nan'},{'direction':'BUY'},{'closed_at':'2025-01-01T00:00:00Z'},{'position_currency':'?'},{'external_id':''}])
def test_bad_rows_are_not_normalized_or_echoed(patch):
    result=preview_statement(statement(**patch),{k:k for k in REQUIRED},'private')
    assert not result['valid'] and result['items']==[] and result['errors'][0]['line']==2
    assert 'private' not in str(result)

def test_duplicate_ids_and_mapping_validation():
    text=statement();row=text.splitlines()[1]
    result=preview_statement(text+'\n'+row,{k:k for k in REQUIRED},'a')
    assert len(result['items'])==1 and len(result['errors'])==1
    with pytest.raises(ValueError):preview_statement(text,{},'a')
