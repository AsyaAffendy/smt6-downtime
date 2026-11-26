import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import EventWork, { ProblemFields } from "../components/EventWork";
import { Badge, ErrorBox, Field, Form, STATUS } from "../components/ui";
import { api } from "../lib/api";
import { useLive } from "../lib/live";
import { fmt, toIso } from "../lib/time";

function StatusPanel({ detail, categories, reload }) {
  const { machine, open_event: event } = detail;
  const [next, setNext] = useState("");
  const options = Object.keys(STATUS).filter((s) => s !== machine.status && !(event && s === "RUNNING"));
  const opening = next === "DOWN" && !event;
  return (
    <section className="panel space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-black">{machine.id}</h2>
        <Badge status={machine.status} />
        {event && <span className="text-sm text-slate-300">{event.event_no} open since {fmt(event.started_at)}</span>}
      </div>
      <div>
        <p className="label">Change status to</p>
        <div className="flex flex-wrap gap-2">
          {options.map((s) => (
            <button key={s} type="button" onClick={() => setNext(s)} aria-pressed={next === s}
              className={`btn ${next === s ? STATUS[s].badge + " ring-2 ring-white" : ""}`}>{s}</button>
          ))}
        </div>
        {event && <p className="mt-2 text-sm text-slate-400">The downtime timer keeps running in every status. To return to RUNNING, confirm production recovery below.</p>}
      </div>
      {next && (
        <Form submit={opening ? "Set DOWN and open downtime event" : `Set ${next}`}
          onSubmit={async (d) => {
            await api.post(`/api/control/machines/${machine.id}/status`, {
              status: next, note: d.note,
              ...(opening && { problem: { description: d.description, category: d.category, root_cause: d.root_cause }, occurred_at: toIso(d.occurred_at) }),
            });
            setNext("");
            await reload();
          }}>
          {opening && (
            <>
              <ProblemFields categories={categories} />
              <Field label="Machine went down at (blank = now)" className="max-w-xs"><input type="datetime-local" name="occurred_at" className="input" /></Field>
            </>
          )}
          <Field label="Note (optional)"><input name="note" className="input" /></Field>
        </Form>
      )}
    </section>
  );
}

export default function Control() {
  const [params, setParams] = useSearchParams();
  const { data } = useLive();
  const [meta, setMeta] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const selected = params.get("machine") || "SMT6-0014";
  const wanted = useRef(selected);
  wanted.current = selected;

  const reload = useCallback(async () => {
    try {
      const result = await api.get(`/api/control/machines/${selected}`);
      if (wanted.current === selected) { setDetail(result); setError(""); } // ignore late replies
    } catch (e) { setError(e.message); }
  }, [selected]);

  useEffect(() => { api.get("/api/meta").then(setMeta).catch((e) => setError(e.message)); }, []);
  useEffect(() => { reload(); }, [reload]);
  // Another user's change arrives over the live feed; refresh without clearing typed forms.
  const card = data?.machines.find((m) => m.id === selected);
  const signature = card && JSON.stringify([card.status, card.status_since, card.event && { ...card.event, duration_seconds: 0 }]);
  useEffect(() => { if (signature) reload(); }, [signature]); // eslint-disable-line
  // Edits invisible on the public feed (actions, parts, root cause) are picked up here.
  useEffect(() => { const i = setInterval(reload, 15000); return () => clearInterval(i); }, [reload]);

  const current = detail?.machine.id === selected ? detail : null;
  return (
    <main className="mx-auto w-full max-w-5xl space-y-4 p-4">
      <nav className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(meta?.machines || []).map((id) => {
          const status = data?.machines.find((m) => m.id === id)?.status;
          return (
            <button key={id} onClick={() => setParams({ machine: id })}
              className={`panel cursor-pointer p-3 text-left ${id === selected ? "!border-sky-400 ring-1 ring-sky-400" : ""}`}>
              <span className="block font-bold">{id}</span>
              <span className="flex items-center gap-2 text-xs text-slate-300"><span className={`size-2.5 rounded-full ${STATUS[status]?.bar}`} />{status}</span>
            </button>
          );
        })}
      </nav>
      <ErrorBox message={error} />
      {current && meta && (
        <div key={selected} className="space-y-4">
          <StatusPanel key={current.machine.status} detail={current} categories={meta.categories} reload={reload} />
          {current.open_event
            ? <EventWork key={current.open_event.id} event={current.open_event} categories={meta.categories} onChange={reload} />
            : <p className="panel p-4 text-slate-400">No open downtime event. Setting the machine DOWN creates one. Closed events are in History &amp; Reports.</p>}
        </div>
      )}
    </main>
  );
}
