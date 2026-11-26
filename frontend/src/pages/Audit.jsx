import { useEffect, useState } from "react";
import { ErrorBox, Field } from "../components/ui";
import { api, query } from "../lib/api";
import { fmtFull } from "../lib/time";

export default function Audit() {
  const [filters, setFilters] = useState({ machine: "", event_no: "" });
  const [page, setPage] = useState(1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.get(`/api/audit?${query({ ...filters, page })}`).then((r) => { setResult(r); setError(""); }).catch((e) => setError(e.message));
  }, [filters, page]);
  const pages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  return (
    <main className="mx-auto w-full max-w-7xl space-y-4 p-4">
      <form className="panel flex flex-wrap items-end gap-3 p-4"
        onSubmit={(e) => { e.preventDefault(); setFilters(Object.fromEntries(new FormData(e.currentTarget))); setPage(1); }}>
        <Field label="Machine"><input name="machine" className="input" placeholder="SMT6-0014" /></Field>
        <Field label="Event number"><input name="event_no" className="input" /></Field>
        <button className="btn btn-primary">Search</button>
      </form>
      <ErrorBox message={error} />
      <section className="panel overflow-x-auto p-2">
        <table className="w-full">
          <thead><tr>{["Time", "User", "Action", "Machine", "Event", "Details"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>
            {result?.items.map((a) => (
              <tr key={a.id}>
                <td className="td whitespace-nowrap">{fmtFull(a.at)}</td>
                <td className="td">{a.user ? `${a.user.name} (${a.user.role})` : "system / anonymous"}</td>
                <td className="td font-mono">{a.action}</td>
                <td className="td whitespace-nowrap">{a.machine_id || "—"}</td>
                <td className="td whitespace-nowrap">{a.event_no || "—"}</td>
                <td className="td max-w-md font-mono text-xs break-all text-slate-300">{JSON.stringify(a.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <div className="flex items-center justify-end gap-3 text-sm">
        <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
        Page {page} of {pages}
        <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </main>
  );
}
