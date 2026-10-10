export const SANDBOX_ACK='Run this quarantined source in Docker on frozen development data only';
export const sandboxActive=run=>['QUEUED','RUNNING'].includes(run?.status);
export function sandboxApproval(control,candidate,seconds=120){
 const parse=value=>{const result=JSON.parse(value);if(!result||Array.isArray(result)||typeof result!=='object'||Object.values(result).some(v=>v===null||!['number','string','boolean'].includes(typeof v)))throw new Error('Parameters must be a JSON object of numbers, strings or booleans.');return result;};
 if(!Number.isInteger(seconds)||seconds<10||seconds>600)throw new Error('Time limit must be 10 to 600 seconds.');
 return {control_parameters:parse(control),candidate_parameters:parse(candidate),timeout_seconds:seconds,acknowledgement:SANDBOX_ACK};
}
