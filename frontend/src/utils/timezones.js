export const TIMEZONE_OPTIONS = [
  { value: "local", label: "Local device time" },
  { value: "America/New_York", label: "New York / US market (ET)" },
  { value: "Europe/London", label: "London (UK)" },
  { value: "UTC", label: "UTC" },
];

export function browserZone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export function resolvedZone(zone) {
  return zone === "local" ? browserZone() : zone;
}

export function zonedInputToIso(value, zone) {
  if (!value) return null;
  if (zone === "local") return new Date(value).toISOString();
  const [datePart, timePart = "00:00"] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute, second = 0] = timePart.split(":").map(Number);
  const desiredUtc = Date.UTC(year, month - 1, day, hour, minute, second);
  let guess = desiredUtc;
  // Two iterations are sufficient across normal offsets and DST transitions.
  for (let i = 0; i < 3; i += 1) {
    const actual = partsInZone(new Date(guess), zone);
    const actualAsUtc = Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute, actual.second);
    guess += desiredUtc - actualAsUtc;
  }
  return new Date(guess).toISOString();
}

export function isoToZonedInput(value, zone) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  if (zone === "local") {
    const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return shifted.toISOString().slice(0, 16);
  }
  const p = partsInZone(date, zone);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

export function nowInZoneInput(zone) {
  return isoToZonedInput(new Date().toISOString(), zone);
}

export function formatInZone(value, zone, options = {}) {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolvedZone(zone),
    dateStyle: "short",
    timeStyle: "short",
    ...options,
  }).format(date);
}

function partsInZone(date, zone) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hourCycle: "h23",
  });
  const out = {};
  for (const part of fmt.formatToParts(date)) {
    if (["year", "month", "day", "hour", "minute", "second"].includes(part.type)) out[part.type] = Number(part.value);
  }
  return out;
}

function pad(v) { return String(v).padStart(2, "0"); }
