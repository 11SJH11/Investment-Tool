import {createContext,useContext} from 'react';
export const WorkflowContext=createContext({open:()=>{},context:null});
export const useWorkflow=()=>useContext(WorkflowContext);
