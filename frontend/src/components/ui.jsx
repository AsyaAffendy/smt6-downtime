import { useState } from "react";
import { fmt, span } from "../lib/time";

export const STATUS = {
  RUNNING: { bar: "bg-emerald-500", badge: "bg-emerald-500 text-emerald-950", border: "border-emerald-700" },
  DOWN: { bar: "bg-red-500", badge: "bg-red-600 text-white", border: "border-red-500" },
  IDLE: { bar: "bg-slate-400", badge: "bg-slate-400 text-slate-950", border: "border-slate-600" },
  SETUP: { bar: "bg-sky-500", badge: "bg-sky-500 text-sky-950", border: "border-sky-700" },
  "TESTING/RECOVERY": { bar: "bg-amber-400", badge: "bg-amber-400 text-amber-950", border: "border-amber-500" },
};

export const Badge = ({ status, className = "" }) => (
  <span className={`inline-block rounded-md px-2.5 py-1 text-sm font-bold tracking-wide ${STATUS[status]?.badge} ${className}`}>
    {status}
  </span>
);

export const ErrorBox = ({ message }) =>
  message ? <div role="alert" className="rounded-lg border border-red-700 bg-red-950 px-4 py-2 text-sm text-red-200">{message}</div> : null;

export const Field = ({ label, children, className = "" }) => (
  <label className={`block ${className}`}><span className="label">{label}</span>{children}</label>
);

/** Form wrapper: blocks double submits, shows the server's error, and resets only on success. */
export function Form({ onSubmit, submit, children, className = "", tone = "btn-primary", disabled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const handle = async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true);
    setError("");
    try {
      await onSubmit(Object.fromEntries(new FormData(form)));
      form.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={handle} className={`space-y-3 ${className}`}>
      {children}
      <ErrorBox message={error} />
      <button className={`btn ${tone}`} disabled={busy || disabled}>{busy ? "Saving…" : submit}</button>
    </form>
  );
}

export function EventTimeline({ event }) {
  return (
    <ol className="space-y-1 text-sm">
      {event.status_history.map((h, i) => (
        <li key={i} className="flex flex-wrap gap-x-3">
          <span className="w-28 shrink-0 font-mono text-slate-400">{fmt(h.at)}</span>
          <span className="font-semibold">{h.status}</span>
          <span className="text-slate-400">{h.by.name}{h.note && ` — ${h.note}`}</span>
        </li>
      ))}
    </ol>
  );
}

export const attendanceSpan = (a) =>
  a.left_at ? span((Date.parse(a.left_at) - Date.parse(a.arrived_at)) / 1000) : "on site";
