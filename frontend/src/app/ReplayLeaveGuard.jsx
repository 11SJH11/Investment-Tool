import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState} from 'react';
const Context=createContext({request:action=>action(),register:()=>()=>{}});
export const useReplayLeaveGuard=()=>useContext(Context);

export default function ReplayLeaveGuard({children}) {
  const handler=useRef(null),dialog=useRef(null),[pending,setPending]=useState(null),[error,setError]=useState('');
  const register=useCallback(get=>{handler.current=get;return()=>{if(handler.current===get)handler.current=null;};},[]);
  const request=useCallback(action=>{
    const current=handler.current?.();
    if(!current?.shouldGuard){action();return true;}
    current.pause();setError('');setPending({action});return false;
  },[]);
  useEffect(()=>{
    const warn=event=>{if(handler.current?.()?.shouldGuard){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[]);
  useEffect(()=>{if(pending&&!dialog.current.open)dialog.current.showModal();},[pending]);
  const leave=save=>{
    try {
      const current=handler.current?.();
      if(current?.busy)throw new Error('Replay is updating. Wait for the current step to finish, then try again.');
      if(save){if(!current)throw new Error('Replay checkpoint is unavailable. Stay and try again.');current.save();}
      const action=pending.action;setPending(null);action();
    }catch(e){setError(e.message||'Checkpoint failed. Replay has not been closed.');}
  };
  const value=useMemo(()=>({request,register,blocked:Boolean(pending)}),[request,register,pending]);
  return <Context.Provider value={value}>{children}{pending&&<dialog ref={dialog} aria-labelledby="replay-leave-title" onCancel={event=>{event.preventDefault();setPending(null);}} className="rounded-xl border border-stone-300 p-6 shadow-xl max-w-lg">
    <h2 id="replay-leave-title" className="text-lg font-semibold">Leave this Replay session?</h2>
    <p className="my-3 text-sm">You have a simulated position, pending order or session changes. A checkpoint saves this session in this browser only; it does not save a trade to Journal.</p>
    {error&&<p role="alert" className="my-3 text-sm text-red-700">{error}</p>}
    <div className="ui-toolbar"><button autoFocus className="mini-btn" onClick={()=>setPending(null)}>Stay</button><button className="mini-btn" onClick={()=>leave(true)}>Save checkpoint and leave</button><button className="mini-btn" onClick={()=>leave(false)}>Leave / discard</button></div>
  </dialog>}</Context.Provider>;
}
