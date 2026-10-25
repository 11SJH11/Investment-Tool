"""Bounded transactional research events. No prompts, results, source or exception text."""
from contextlib import closing
from datetime import datetime, timezone
import json
import traceback

MAX_EVENTS = 10000
MAX_CAMPAIGN_EVENTS = 1000
ERRORS = {
    'unknown_evidence_reference': ('UNKNOWN_EVIDENCE_REFERENCE', 'Model cited evidence outside the supplied map.'),
    'proposal_variant_budget': ('PROPOSAL_VARIANT_BUDGET', 'Proposed simulations exceed the authorized limit.'),
    'model_rate_limited': ('MODEL_RATE_LIMITED', 'Provider rate limit rejected the call.'),
    'model_authentication': ('MODEL_AUTHENTICATION', 'Provider authentication failed.'),
    'model_provider_error': ('MODEL_PROVIDER_ERROR', 'Provider returned an unsuccessful response.'),
    'model_timeout': ('MODEL_TIMEOUT', 'Model request exceeded its timeout.'),
    'model_incomplete': ('MODEL_INCOMPLETE', 'Provider did not complete the requested output.'),
    'model_refusal': ('MODEL_REFUSAL', 'Provider refused the request.'),
    'model_invalid_output': ('MODEL_INVALID_OUTPUT', 'Provider output failed validation.'),
    'model_invalid_output_or_transport_failure': ('MODEL_OUTPUT_OR_TRANSPORT', 'Provider transport or output validation failed.'),
    'acceptance_budget_blocked': ('MODEL_BUDGET_BLOCKED', 'The acceptance spending guard blocked the request.'),
    'usage_exceeded_cost_reservation': ('MODEL_USAGE_EXCEEDED', 'Reported usage exceeded the reservation.'),
    'project_not_active': ('AUTHORIZATION_REVOKED', 'Project authority no longer permits this operation.'),
    'review_deadline': ('MODEL_DEADLINE', 'The review deadline expired.'),
    'invalid_committee_output': ('COMMITTEE_VALIDATION', 'Committee output failed validation.'),
    'author_validation_failed': ('AUTHOR_VALIDATION', 'Code Author output failed validation.'),
    'required_history_missing': ('REQUIRED_HISTORY_MISSING','Required historical inputs are not cached.'),
    'required_history_incomplete': ('REQUIRED_HISTORY_INCOMPLETE','Required timeframes are incomplete or use different providers.'),
    'strategy_instrument_unsupported': ('STRATEGY_INSTRUMENT_UNSUPPORTED','The selected strategy does not support this market.'),
    'insufficient_history': ('INSUFFICIENT_HISTORY','Insufficient completed sessions for the declared dataset policy.'),
    'backtest_failed': ('BACKTEST_FAILED','Backtest worker failed. Inspect the linked job and private exception frames.'),
    'sandbox_failed': ('SANDBOX_FAILED','Isolated generated-strategy evaluation failed.'),
    'campaign_operation_failed': ('CAMPAIGN_OPERATION_FAILED','Campaign lifecycle operation failed.'),
}


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS agent_diagnostics(
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
        document TEXT NOT NULL, private_trace TEXT)''')
    c.execute('CREATE INDEX IF NOT EXISTS agent_diagnostics_campaign ON agent_diagnostics(campaign_id,id)')


def private_trace(exc):
    """Keep causal frame locations without paths, source lines, locals or exception args."""
    chain=[]; seen=set()
    while exc is not None and id(exc) not in seen and len(chain)<8:
        seen.add(id(exc))
        frames=[{'file': f.filename.replace('\\','/').rsplit('/',1)[-1][:100],
                 'line': f.lineno, 'function': f.name[:100]}
                for f in traceback.extract_tb(exc.__traceback__)[-24:]]
        chain.append({'class':type(exc).__name__[:100], 'frames':frames})
        exc=exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return chain


def append(c, campaign_id, *, component, operation, status, operation_id=None,
           project_id=None, error=None, trace=None, phase=None):
    if not campaign_id:return
    initialize(c)
    code,message=ERRORS.get(error, ('OPERATION_FAILED','Research operation failed; inspect private backend diagnostics.')) if error else (None,'Recorded research lifecycle transition.')
    event=dict(timestamp=datetime.now(timezone.utc).isoformat(),campaign_id=campaign_id,
               component=component,operation=operation,status=status,
               operation_id=operation_id,project_id=project_id,correlation_id=operation_id or campaign_id,
               parent_operation_id=project_id,family=None,phase=phase,
               level='ERROR' if error else 'INFO',error_code=code,message=message,
               retryable=False,suggested_action='Inspect the operation and authority before manually retrying.' if error else None)
    if project_id and c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_projects'").fetchone():
        project=c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()
        if project:
            family=json.loads(project[0]).get('campaign_family_id')
            if isinstance(family,str) and len(family)<=150:event['family']=family
    c.execute('INSERT INTO agent_diagnostics(campaign_id,document,private_trace) VALUES(?,?,?)',
              (campaign_id,json.dumps(event),json.dumps(trace) if trace else None))
    # AUTOINCREMENT prevents cursor reuse after pruning, even when a campaign is removed.
    c.execute('DELETE FROM agent_diagnostics WHERE campaign_id=? AND id NOT IN '
              '(SELECT id FROM agent_diagnostics WHERE campaign_id=? ORDER BY id DESC LIMIT ?)',
              (campaign_id,campaign_id,MAX_CAMPAIGN_EVENTS))
    c.execute('DELETE FROM agent_diagnostics WHERE id <= COALESCE('
              '(SELECT id FROM agent_diagnostics ORDER BY id DESC LIMIT 1 OFFSET ?),-1)',(MAX_EVENTS,))


def review_transition(c, before, after):
    def state(row):
        op=row.get('operation') or {}
        return row.get('status'),op.get('role'),op.get('status')
    if state(before)==state(after):return
    project=c.execute('SELECT document FROM agent_projects WHERE id=?',(after['project_id'],)).fetchone()
    campaign=json.loads(project[0]).get('campaign_id') if project else None
    op=after.get('operation') or {}
    append(c,campaign,component='research.code_author' if after.get('kind')=='CODE_AUTHOR' else 'research.committee',
           operation=op.get('role') if op.get('role') in {'Researcher','Devil','Manager','CodeAuthor'} else 'review',
           status=after['status'],operation_id=after['id'],project_id=after['project_id'],
           phase=after.get('diagnostic_stage'),
           error=after.get('error') if after['status']=='FAILED' else None,
           trace=after.pop('_private_diagnostic_trace',None))


def page(database,campaign_id,after=0,limit=100):
    if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('Invalid diagnostic cursor or limit')
    with closing(database.connect()) as c:
        if not c.execute('SELECT 1 FROM agent_campaigns WHERE id=?',(campaign_id,)).fetchone():
            raise ValueError('Unknown campaign')
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_diagnostics'").fetchone():
            return dict(items=[],next_after=after,has_more=False,retention_gap=False)
        first=c.execute('SELECT MIN(id) FROM agent_diagnostics WHERE campaign_id=?',(campaign_id,)).fetchone()[0]
        rows=c.execute('SELECT id,document FROM agent_diagnostics WHERE campaign_id=? AND id>? ORDER BY id LIMIT ?',
                       (campaign_id,after,limit+1)).fetchall()
        items=[dict(json.loads(row[1]),event_id=row[0]) for row in rows[:limit]]
        return dict(items=items,next_after=items[-1]['event_id'] if items else after,
                    has_more=len(rows)>limit,retention_gap=bool(after and first and after<first-1))
