import {useEffect, useRef, useState} from 'react';
import {readUI, writeUI} from './uiPreferences.js';
export function useUIPreference(key, fallback) {
  const [value, setValue] = useState(() => readUI(key, fallback));
  const defaults=useRef(fallback); defaults.current=fallback;
  useEffect(()=>{const reset=e=>{if(e.detail?.includes(key))setValue(defaults.current);};window.addEventListener('ledger:reset-view',reset);return()=>window.removeEventListener('ledger:reset-view',reset);},[key]);
  useEffect(() => writeUI(key, value), [key, value]);
  return [value, setValue];
}
