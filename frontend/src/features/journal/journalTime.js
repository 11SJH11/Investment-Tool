import { isoToZonedInput, resolvedZone, zonedInputToIso } from '../../utils/timezones.js';
// Journal-only validation; chart/replay conversion behaviour stays intact.
export function journalInputToIso(value, zone) {
  if(!value)return null;
  const actualZone=resolvedZone(zone),iso=zonedInputToIso(value,actualZone),minute=value.slice(0,16);
  if(isoToZonedInput(iso,actualZone)!==minute)throw new Error('This local time does not exist. Check the date or daylight-saving change.');
  for(const shift of [-120,-60,-30,30,60,120])if(isoToZonedInput(new Date(Date.parse(iso)+shift*60000).toISOString(),actualZone)===minute)throw new Error('This local time occurs twice during a daylight-saving change. Select UTC as the input timezone and enter the exact UTC time.');
  return iso;
}
