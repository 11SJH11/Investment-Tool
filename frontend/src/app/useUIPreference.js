import {useEffect, useState} from 'react';
import {readUI, writeUI} from './uiPreferences.js';
export function useUIPreference(key, fallback) {
  const [value, setValue] = useState(() => readUI(key, fallback));
  useEffect(() => writeUI(key, value), [key, value]);
  return [value, setValue];
}
