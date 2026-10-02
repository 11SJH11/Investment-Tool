import {api} from '../../api/client.js';
import {activeStatus,createStatusPoller} from './statusPolling.js';
export const jobStatus=createStatusPoller(()=>api.backtestJobs(),data=>(data.jobs||[]).some(job=>activeStatus(job.status))||data.compute?.used_workers>0);
export const researchHistoryStatus=createStatusPoller(()=>api.researchExperiments(),data=>(data.experiments||[]).some(item=>activeStatus(item.status)),3000);
