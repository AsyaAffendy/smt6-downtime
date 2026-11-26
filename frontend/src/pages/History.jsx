import { useCallback, useEffect, useRef, useState } from "react";
import EventWork from "../components/EventWork";
import { ErrorBox, Field } from "../components/ui";
import { api, query } from "../lib/api";
import { fmt, fmtFull, span } from "../lib/time";

const EMPTY = { machine: "", date_from: "", date_to: "", q: "", state: "", category: "" };

const Fixed = ({ children }) => <span className="whitespace-nowrap">{children}</span>;

const Stat = ({ label, value }) => (
  <div className="panel p-4"><p className="label">{label}</p><p className="text-2xl font-bold">{value}</p></div>
);

const Table = ({ title, heads, rows, empty = "No data for these filters." }) => (
  <section className="panel overflow-x-auto p-2">
    <h2 className="px-3 py-2 font-bold">{title}</h2>
    {rows.length === 0 ? <p className="px-3 pb-3 text-sm text-slate-400">{empty}</p> : (
      <table className="w-full">
        <thead><tr>{heads.map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="td">{c}</td>)}</tr>)}</tbody>
      </table>
    )}
  </section>
);

function Bar({ value, max }) {
  return (
    <div className="flex min-w-32 items-center gap-2">
      <div className="h-3 flex-1 rounded bg-slate-800"><div className="h-3 rounded bg-sky-500" style={{ width: `${max ? (value / max) * 100 : 0}%` }} /></div>
      <b className="w-6 text-right">{value}</b>
    </div>
  );
}

export default function History() {
  const [filters, setFilters] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [meta, setMeta] = useState({ machines: [], categories: [] });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const detail = useRef(null);
  useEffect(() => { detail.current?.scrollIntoView({ behavior: "smooth" }); }, [selected?.id]);

  const load = useCallback(() =>
    api.get(`/api/history/events?${query({ ...filters, page })}`)
      .then((r) => { setResult(r); setError(""); }).catch((e) => setError(e.message)), [filters, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/api/meta").then(setMeta).catch(() => {}); }, []);

  const open = (id) => api.get(`/api/history/events/${id}`).then(setSelected).catch((e) => setError(e.message));
  const apply = (e) => {
    e.preventDefault();
    setFilters({ ...EMPTY, ...Object.fromEntries(new FormData(e.currentTarget)) });
    setPage(1); setSelected(null);
  };
  const exportAs = (type) =>
    api.download(`/api/history/export.${type}?${query(filters)}`, `smt6-downtime.${type}`).catch((e) => setError(e.message));

  const s = result?.summary;
  const pages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  const select = (name, label, options) => (
    <Field label={label}><select name={name} className="input"><option value="">All</option>{options.map((o) => <option key={o}>{o}</option>)}</select></Field>
  );

  return (
    <main className="mx-auto w-full max-w-7xl space-y-4 p-4">
      <form onSubmit={apply} onReset={() => { setFilters(EMPTY); setPage(1); setSelected(null); }}
        className="panel grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-6">
        {select("machine", "Machine", meta.machines)}
        <Field label="Down from"><input type="date" name="date_from" className="input" /></Field>
        <Field label="Down to"><input type="date" name="date_to" className="input" /></Field>
        {select("state", "Event status", ["OPEN", "CLOSED"])}
        {select("category", "Category", meta.categories)}
        <Field label="Problem search"><input name="q" className="input" placeholder="problem, cause, part…" /></Field>
        <div className="flex flex-wrap gap-2 sm:col-span-3 lg:col-span-6">
          <button className="btn btn-primary">Search</button>
          <button type="reset" className="btn">Clear</button>
          <span className="flex-1" />
          <button type="button" className="btn" onClick={() => exportAs("csv")}>Export CSV</button>
          <button type="button" className="btn" onClick={() => exportAs("xlsx")}>Export Excel</button>
        </div>
      </form>
      <ErrorBox message={error} />
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Breakdowns" value={s.breakdowns} />
            <Stat label="Still open" value={s.open} />
            <Stat label="Total downtime" value={span(s.total_seconds)} />
            <Stat label="Average per event" value={span(s.average_seconds)} />
            <Stat label="Avg. technician response" value={span(s.average_response_seconds)} />
          </div>
          <Table title="Downtime events" empty="No events match these filters."
            heads={["Event", "Machine", "Down at", "Recovered", "Duration", "Problems", "Technicians", "State"]}
            rows={result.items.map((e) => [
              <button className="cursor-pointer font-semibold whitespace-nowrap text-sky-300 underline" onClick={() => open(e.id)}>{e.event_no}</button>,
              <span className="whitespace-nowrap">{e.machine_id}</span>, <Fixed>{fmtFull(e.started_at)}</Fixed>, <Fixed>{fmtFull(e.recovered_at)}</Fixed>, <Fixed>{span(e.duration_seconds)}</Fixed>,
              <span>{e.problems.map((p) => p.description).join("; ")}</span>,
              [...new Set(e.attendance.map((a) => a.technician_name))].join(", ") || "—",
              <b className={e.state === "OPEN" ? "text-red-400" : "text-emerald-400"}>{e.state}</b>,
            ])} />
          <div className="flex items-center justify-end gap-3 text-sm">
            <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            Page {page} of {pages}
            <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
          {selected && (
            <section className="space-y-3 rounded-xl border border-sky-700 p-4" ref={detail} key={selected.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-xl font-bold">{selected.event_no} · {selected.machine_id} · {selected.state} · {span(selected.duration_seconds)}</h2>
                <button className="btn" onClick={() => setSelected(null)}>Close view</button>
              </div>
              {selected.recovery && <p className="text-sm">Recovery confirmed by <b>{selected.recovery.confirmed_by.name}</b> (recorded {fmt(selected.recovery.confirmed_at)}): {selected.recovery.note}</p>}
              <EventWork event={selected} categories={meta.categories} onChange={async () => { await open(selected.id); await load(); }} />
            </section>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Table title="Breakdown frequency by machine" heads={["Machine", "Breakdowns", "Total downtime", "Average"]}
              rows={s.by_machine.map((m) => [m.machine_id,
                <Bar value={m.breakdowns} max={Math.max(...s.by_machine.map((x) => x.breakdowns))} />, span(m.total_seconds), span(m.average_seconds)])} />
            <Table title="Problems by category" heads={["Category", "Problems"]}
              rows={s.problems_by_category.map((c) => [c.category, <Bar value={c.count} max={s.problems_by_category[0].count} />])} />
          </div>
          <Table title="Technician attendance" heads={["Technician", "Events attended", "Visits", "Time on events"]}
            rows={s.technicians.map((t) => [t.name, t.events, t.visits, span(t.seconds)])} />
          <p className="text-xs text-slate-500">Date filters use the DOWN time. Open events count up to now. Technician time on overlapping events is added for each event.</p>
        </>
      )}
    </main>
  );
}
