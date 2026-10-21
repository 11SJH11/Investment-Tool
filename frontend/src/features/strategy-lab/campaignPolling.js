import {campaignIsRunning,campaignValidationPending} from './campaignView.js';

// Serial, read-only polling: never retry campaign mutations or overlap requests.
export function pollCampaign({fetchReport,onReport,onConnection,schedule=setTimeout,cancel=clearTimeout,now=Date.now}){
 let stopped=false,timer,failures=0,lastSuccess=null;
 const poll=async()=>{
  try{
   const report=await fetchReport();
   if(stopped)return;
   failures=0;lastSuccess=now();
   onReport(report);onConnection({error:null,lastSuccess,retryMs:null});
   if(campaignIsRunning(report.campaign.status)||campaignValidationPending(report.campaign))timer=schedule(poll,2500);
  }catch(error){
   if(stopped)return;
   const retryMs=Math.min(30000,2500*2**Math.min(failures++,4));
   onConnection({error:error.message||'Campaign refresh failed',lastSuccess,retryMs});
   timer=schedule(poll,retryMs);
  }
 };
 poll();
 return()=>{stopped=true;cancel(timer);};
}
