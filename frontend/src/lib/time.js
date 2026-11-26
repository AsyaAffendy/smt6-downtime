// The plant time zone comes from the server so every screen shows factory time.
let zone = "Asia/Kuala_Lumpur";
export const setZone = (z) => { zone = z; };

export const fmt = (iso) =>
  iso ? new Intl.DateTimeFormat("en-GB", { timeZone: zone, day: "2-digit", month: "short",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso)) : "—";

// For records: includes the year.
export const fmtFull = (iso) =>
  iso ? new Intl.DateTimeFormat("en-GB", { timeZone: zone, day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso)) : "—";

export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

export function span(seconds) {
  if (seconds == null) return "—";
  const m = Math.round(seconds / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

// <input type="datetime-local"> is in the device's local time; send it with an explicit offset.
export const toIso = (local) => (local ? new Date(local).toISOString() : null);
