from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone
import sqlite3
import pytest
from app.core.safe_errors import safe_failure,MissingHistoryError,MissingHistoryParameterError,ProviderConfigurationError
from app.data.http import ProviderHttpError
from app.services.backtest_jobs import BacktestJobs
from app.storage.database import Database
from tests.test_backtest_jobs import wait_for

SECRET='token=secret-password https://private.example/account/123'
@pytest.mark.parametrize('exc,category',[
 (ProviderHttpError(SECRET,status_code=401),'authentication'),
 (ProviderHttpError(SECRET,status_code=403),'entitlement'),
 (ProviderConfigurationError(SECRET),'authentication'),
 (MissingHistoryError(SECRET),'missing_history'),
 (MissingHistoryParameterError(SECRET),'missing_history'),
 (ValueError(SECRET),'invalid_parameters'),
 (TypeError(SECRET),'invalid_parameters'),
 (OSError(SECRET),'storage'),
 (sqlite3.OperationalError(SECRET),'storage'),
 (BrokenProcessPool(SECRET),'worker_termination'),
 (ConnectionError(SECRET),'provider'),
 (TimeoutError(SECRET),'provider'),
 (ProviderHttpError(SECRET,status_code=503),'provider'),
 (RuntimeError(SECRET),'unknown'),
])
def test_allowlisted_categories_never_copy_exception_details(exc,category):
 result=safe_failure(exc);assert result[0]==category
 assert 'secret' not in str(result) and 'private.example' not in str(result)
 assert result[2] is None

@pytest.mark.parametrize('delay,seconds',[(120,120),(None,60),('broken',60),(float('nan'),60),(float('inf'),60),(-1,60)])
def test_cooldown_is_numeric_safe_and_has_exact_retry_time(delay,seconds):
 now=datetime(2026,10,2,tzinfo=timezone.utc)
 result=safe_failure(ProviderHttpError(SECRET,status_code=429,retry_after=delay),now=now)
 assert result[0]=='rate_limited'
 assert (datetime.fromisoformat(result[2])-now).total_seconds()==seconds
 assert result[2] in result[1] and 'secret' not in str(result)

def test_strategy_value_error_is_not_assumed_to_be_user_parameter_error():
 assert safe_failure(ValueError(SECRET),default='strategy_execution')[0]=='strategy_execution'

def test_queue_persists_safe_rate_limit_message_and_compact_api_projection(tmp_path):
 db=Database(tmp_path/'safe.db');db.initialize()
 class Service:
  def run(self,*args,**kwargs):raise ProviderHttpError(SECRET,status_code=429,retry_after=120)
 queue=BacktestJobs(db,Service(),workers=1)
 try:
  job=queue.enqueue([{'symbols':['NQ1!']}],'safe-fixture')[0]
  wait_for(lambda:queue.get(job['id'])['status']=='failed')
  for row in (queue.get(job['id']),queue.compact_list()[0]):
   assert '[rate_limited]' in row['error'] and 'Retry no earlier' in row['error']
   assert 'secret' not in str(row) and 'private.example' not in str(row)
 finally:queue.close()
