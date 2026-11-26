import { useState } from "react";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { fmt, toIso } from "../lib/time";
import { EventTimeline, Field, Form, attendanceSpan } from "./ui";

export function ProblemFields({ categories, value = {} }) {
  return (
    <>
      <Field label="Problem description">
        <textarea name="description" required maxLength={2000} rows={2} className="input" defaultValue={value.description} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Category">
          <select name="category" className="input" defaultValue={value.category || "Unclassified"}>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Root cause (if known)">
          <input name="root_cause" maxLength={2000} className="input" defaultValue={value.root_cause} />
        </Field>
      </div>
    </>
  );
}

const Drawer = ({ title, children }) => (
  <details className="rounded-lg border border-slate-800 bg-slate-950/50">
    <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-sky-300">{title}</summary>
    <div className="p-3">{children}</div>
  </details>
);

function ProblemEditor({ problem, categories, onSave }) {
  // Once typing starts, hold on to that version: refreshes must not wipe the text,
  // and a colleague's newer change must not be overwritten.
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const shown = draft || problem;
  const conflict = !saving && shown.revision !== problem.revision;
  return (
    <div onInput={() => setDraft((d) => d || problem)} className="space-y-3">
      {conflict && (
        <div role="alert" className="rounded-lg border border-amber-600 bg-amber-950 p-3 text-sm text-amber-200">
          Someone else changed this problem while you were editing. Copy anything you need, then{" "}
          <button type="button" className="cursor-pointer font-bold underline" onClick={() => setDraft(null)}>load the latest version</button>.
        </div>
      )}
      <Form key={shown.revision} submit="Save changes" disabled={conflict}
        onSubmit={async (d) => {
          setSaving(true);
          try { await onSave({ ...d, expected_revision: shown.revision }); setDraft(null); }
          finally { setSaving(false); }
        }}>
        <ProblemFields categories={categories} value={shown} />
        <Field label="Problem status">
          <select name="status" className="input" defaultValue={shown.status}><option>OPEN</option><option>RESOLVED</option></select>
        </Field>
      </Form>
    </div>
  );
}

function Problem({ event, problem, index, categories, send, editable }) {
  const base = `/api/events/${event.id}/problems/${problem.id}`;
  const [part, setPart] = useState("STORE");
  return (
    <div className="panel space-y-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">#{index + 1} {problem.description}</p>
          <p className="text-sm text-slate-400">
            {problem.category} · Root cause: {problem.root_cause || "not yet identified"}
          </p>
          <p className="text-xs text-slate-500">
            Added {fmt(problem.created_at)} by {problem.created_by.name} · Updated {fmt(problem.updated_at)} by {problem.updated_by.name}
          </p>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-bold ${problem.status === "OPEN" ? "bg-red-900 text-red-200" : "bg-emerald-900 text-emerald-200"}`}>
          {problem.status}
        </span>
      </div>
      {["TROUBLESHOOTING", "CORRECTIVE"].map((type) => {
        const list = problem.actions.filter((a) => a.type === type);
        return list.length > 0 && (
          <div key={type}>
            <p className="label">{type === "CORRECTIVE" ? "Corrective actions" : "Troubleshooting"}</p>
            <ul className="space-y-1 text-sm">
              {list.map((a) => <li key={a.id}>• {a.description} <span className="text-slate-500">({a.by.name}, {fmt(a.at)})</span></li>)}
            </ul>
          </div>
        );
      })}
      {problem.parts.length > 0 && (
        <div>
          <p className="label">Parts used</p>
          <ul className="space-y-1 text-sm">
            {problem.parts.map((p) => (
              <li key={p.id}>• {p.quantity} × {p.part_name} {p.part_number && `[${p.part_number}]`} —{" "}
                {p.source === "DONOR_MACHINE" ? `from donor machine ${p.donor_machine}${p.donor_details ? ` (${p.donor_details})` : ""}` : p.source === "STORE" ? "from store" : "other source"}
                <span className="text-slate-500"> ({p.by.name}, {fmt(p.at)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div className="space-y-2">
          <Drawer title="Add troubleshooting / corrective action">
            <Form submit="Add action" onSubmit={(d) => send("post", `${base}/actions`, d)}>
              <Field label="Type">
                <select name="type" className="input">
                  <option value="TROUBLESHOOTING">Troubleshooting</option>
                  <option value="CORRECTIVE">Corrective action</option>
                </select>
              </Field>
              <Field label="What was done"><textarea name="description" required rows={2} className="input" /></Field>
            </Form>
          </Drawer>
          <Drawer title="Add part used">
            <Form submit="Add part" onSubmit={async (d) => { await send("post", `${base}/parts`, { ...d, quantity: Number(d.quantity) }); setPart("STORE"); }}>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Part name"><input name="part_name" required className="input" /></Field>
                <Field label="Part number"><input name="part_number" className="input" /></Field>
                <Field label="Quantity"><input name="quantity" type="number" min="1" max="10000" defaultValue="1" required className="input" /></Field>
              </div>
              <Field label="Source">
                <select name="source" className="input" value={part} onChange={(e) => setPart(e.target.value)}>
                  <option value="STORE">Store</option><option value="DONOR_MACHINE">Donor machine</option><option value="OTHER">Other</option>
                </select>
              </Field>
              {part === "DONOR_MACHINE" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Donor machine ID"><input name="donor_machine" required className="input" /></Field>
                  <Field label="Donor details (position, serial, follow-up)"><input name="donor_details" className="input" /></Field>
                </div>
              )}
            </Form>
          </Drawer>
          <Drawer title="Update problem / root cause / status">
            <ProblemEditor problem={problem} categories={categories} onSave={(body) => send("patch", base, body)} />
          </Drawer>
        </div>
      )}
    </div>
  );
}

export default function EventWork({ event, categories, onChange }) {
  const { can, user } = useAuth();
  const open = event.state === "OPEN";
  const editable = open ? can("event.work") : can("event.amend_closed");
  const send = async (method, path, body) => { await api[method](path, body); await onChange(); };
  const base = `/api/events/${event.id}`;
  const unresolved = event.problems.filter((p) => p.status === "OPEN").length;

  return (
    <div className="space-y-5">
      <section className="space-y-3">
        <h3 className="text-lg font-bold">Problems in this event ({event.problems.length})</h3>
        {event.problems.map((p, i) => (
          <Problem key={p.id} index={i} event={event} problem={p} categories={categories} send={send} editable={editable} />
        ))}
        {open && can("event.work") && (
          <Drawer title="＋ Add another problem found during this breakdown">
            <Form submit="Add to this event" onSubmit={(d) => send("post", `${base}/problems`, d)}>
              <ProblemFields categories={categories} />
            </Form>
          </Drawer>
        )}
      </section>

      <section className="panel space-y-3 p-4">
        <h3 className="text-lg font-bold">Technician attendance</h3>
        {event.attendance.length === 0 && <p className="text-sm text-slate-400">No technician recorded yet.</p>}
        {event.attendance.map((a) => (
          <div key={a.id} className="space-y-2 border-t border-slate-800 pt-2 text-sm">
            <p><b>{a.technician_name}</b> · arrived {fmt(a.arrived_at)} · {a.left_at ? `left ${fmt(a.left_at)}` : "still attending"} ({attendanceSpan(a)})
              {a.auto_checkout && " · auto check-out at recovery"}{a.note && ` · ${a.note}`}
              <span className="text-slate-500"> · recorded by {a.recorded_by.name}</span></p>
            {open && !a.left_at && can("event.work") && (
              <Form submit={`Check out ${a.technician_name}`} tone=""
                onSubmit={(d) => send("post", `${base}/attendance/${a.id}/checkout`, { left_at: toIso(d.left_at) })}>
                <Field label="Departure time (blank = now)" className="max-w-xs"><input type="datetime-local" name="left_at" className="input" /></Field>
              </Form>
            )}
          </div>
        ))}
        {open && can("event.work") && (
          <Drawer title="Check in a technician">
            <Form submit="Check in" onSubmit={(d) => send("post", `${base}/attendance`, {
              technician_name: d.technician_name.trim() || null, arrived_at: toIso(d.arrived_at), note: d.note })}>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Technician"><input name="technician_name" className="input" placeholder={`${user.name} (me)`} /></Field>
                <Field label="Arrival time (blank = now)"><input type="datetime-local" name="arrived_at" className="input" /></Field>
                <Field label="Note"><input name="note" className="input" /></Field>
              </div>
            </Form>
          </Drawer>
        )}
      </section>

      {open && can("event.recover") && (
        <section className="rounded-xl border-2 border-emerald-800 bg-emerald-950/30 p-4">
          <h3 className="text-lg font-bold">Confirm production recovery</h3>
          <p className="mb-3 text-sm text-slate-300">This is the only action that stops the downtime timer. Testing alone is not recovery.</p>
          {unresolved > 0 && <p className="mb-3 text-sm font-semibold text-amber-300">⚠ {unresolved} problem(s) still marked OPEN. After closing, only a supervisor can amend them.</p>}
          <Form submit="Close event and set RUNNING" tone="btn-success"
            onSubmit={(d) => send("post", `${base}/recovery`, {
              production_confirmed: d.confirmed === "on", verification_note: d.verification_note, recovered_at: toIso(d.recovered_at) })}>
            <Field label="How was production recovery verified?">
              <input name="verification_note" required className="input" placeholder="e.g. number of good boards produced and who checked" />
            </Field>
            <Field label="Production resumed at (blank = now)" className="max-w-xs"><input type="datetime-local" name="recovered_at" className="input" /></Field>
            <label className="flex items-center gap-2 text-sm font-semibold">
              <input type="checkbox" name="confirmed" required className="size-5" /> I confirm actual production has resumed
            </label>
          </Form>
        </section>
      )}

      <section className="panel p-4">
        <h3 className="mb-2 text-lg font-bold">Status timeline</h3>
        <EventTimeline event={event} />
      </section>
    </div>
  );
}
