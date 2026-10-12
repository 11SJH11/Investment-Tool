export const LAUNCH_CONSENT='Authorize this bounded campaign, provider preparation and the selected model/code permissions';
export const campaignActions=status=>status==='PAUSED'?['resume','cancel']:status==='ACTIVE'?['pause','stop_after_current','cancel']:['PREPARING','STOPPING'].includes(status)?['pause','cancel']:['DRAFT','PREPARED'].includes(status)?['cancel']:[];
export const campaignIsRunning=status=>['DRAFT','PREPARING','PREPARED','ACTIVE','STOPPING'].includes(status);

export function campaignPayload(form,policy,requestKey){
 const symbols=[...new Set(form.symbols.split(/[\s,]+/).filter(Boolean).map(s=>s.toUpperCase()))];
 if(!symbols.length)throw new Error('Enter at least one symbol.');
 const engine={};
 for(const key of ['starting_balance','risk_value','commission_per_order','spread_bps','slippage_bps','max_leverage']){
  const value=Number(form[key]);
  if(form[key]===''||!Number.isFinite(value)||value<0)throw new Error('Enter valid account, risk and cost values.');
  engine[key]=value;
 }
 if(engine.starting_balance<=0||engine.risk_value<=0||engine.max_leverage<=0)throw new Error('Balance, risk and leverage must be positive.');
 engine.sizing_mode='risk_pct';engine.session='regular';
 if(form.mode==='IMPROVE_STRATEGY'&&!form.strategy_key)throw new Error('Select a strategy.');
 const structuralCycles=Number(form.structural_cycles??1);
 if(!Number.isInteger(structuralCycles)||structuralCycles<1||structuralCycles>3)throw new Error('Choose one to three structural attempts.');
 return {campaign:{request_key:requestKey,mode:form.mode,prompt:form.prompt,
   strategy_key:form.mode==='IMPROVE_STRATEGY'?form.strategy_key:null,
   policy:{...policy,symbols,timeframes:[form.timeframe],send_development_summaries:form.model,
     code_generation:form.model&&form.structural,max_structural_hypotheses_per_family:structuralCycles,external_research:false}},engine,
   numeric_cycles:form.model?Number(form.numeric_cycles):0,structural:form.model&&form.structural,
   history:form.history,lookback_days:1460,consent:LAUNCH_CONSENT};
}
