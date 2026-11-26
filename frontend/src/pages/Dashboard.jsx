import { Badge, STATUS } from "../components/ui";
import { useLive, useNow } from "../lib/live";
import { clock, fmt, span } from "../lib/time";

function MachineCard({ m, elapsed, serverNow, live }) {
  const s = STATUS[m.status];
  const ev = m.event;
  return (
    <article className={`machine-card panel flex min-h-72 flex-col overflow-hidden border-2 ${s.border}`}>
      <div className={`h-3 ${s.bar}`} />
      <div className="machine-body flex flex-1 flex-col gap-3 p-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-3xl font-black tracking-tight 2xl:text-4xl">{m.id}</h2>
          <Badge status={m.status} className="!text-xl 2xl:!text-2xl" />
        </header>
        {ev ? (
          <>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="label">Downtime duration{m.status !== "DOWN" && " · event still open"}{!live && " (last known)"}</p>
                <p className="timer font-mono text-5xl font-bold tabular-nums 2xl:text-6xl">{clock(ev.duration_seconds + elapsed)}</p>
              </div>
              <p className="text-right text-sm text-slate-400">{ev.event_no}<br />Down since {fmt(ev.started_at)}</p>
            </div>
            <div>
              <p className="label">Current problem{ev.problem_count > 1 && ` · ${ev.problem_count} recorded in this event`}</p>
              <ul className="space-y-1">
                {ev.problems.slice(-2).reverse().map((p, i) => (
                  <li key={i} className="line-clamp-2 text-lg leading-snug">
                    {p.description} <span className="text-sm text-slate-400">({p.category}{p.status === "RESOLVED" && ", resolved"})</span>
                  </li>
                ))}
              </ul>
              {ev.problems.length > 2 && <p className="text-sm text-slate-400">+ {ev.problems.length - 2} more open</p>}
            </div>
            <div className="mt-auto border-t border-slate-800 pt-3">
              <p className="label">Technician attending</p>
              {ev.technicians.length
                ? <p className="text-xl font-semibold">{ev.technicians.join(", ")}</p>
                : <p className="text-xl font-bold text-amber-300">⚠ No technician checked in</p>}
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center text-center">
            <p className="text-2xl font-semibold text-slate-300">No open downtime</p>
            {m.status_since && (
              <p className="mt-1 text-slate-400">
                {m.status} for {span((serverNow - Date.parse(m.status_since)) / 1000)} · since {fmt(m.status_since)}
              </p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

export default function Dashboard() {
  const { data, offset, connected, received } = useLive();
  const now = useNow();
  if (!data) return <p className="p-10 text-center text-xl text-slate-400">{connected ? "Loading…" : "Connecting to server…"}</p>;
  // Timers freeze if the feed is lost, so a disconnected screen never looks live.
  const elapsed = connected ? Math.max(0, (now - received) / 1000) : 0;
  return (
    <main className="mx-auto w-full max-w-[1900px] space-y-4 p-4">
      {!connected && (
        <div role="alert" className="rounded-lg bg-amber-400 px-4 py-3 text-center text-lg font-bold text-amber-950">
          LIVE CONNECTION LOST — data may be out of date (last update {fmt(new Date(received).toISOString())}). Reconnecting…
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {Object.keys(STATUS).map((status) => (
          <span key={status} className="panel flex items-center gap-2 px-3 py-1.5 text-sm font-semibold">
            <span className={`size-3 rounded-full ${STATUS[status].bar}`} />
            {status} <b className="text-lg">{data.machines.filter((m) => m.status === status).length}</b>
          </span>
        ))}
        <span className="ml-auto text-sm text-slate-400">
          <span className={connected ? "text-emerald-400" : "text-amber-400"}>●</span> {connected ? "Live" : "Offline"} ·{" "}
          {fmt(new Date(now + offset).toISOString())}
        </span>
      </div>
      <section className={`grid gap-4 lg:grid-cols-2 ${connected ? "" : "opacity-60"}`}>
        {data.machines.map((m) => <MachineCard key={m.id} m={m} elapsed={elapsed} serverNow={now + offset} live={connected} />)}
      </section>
      <p className="text-center text-xs text-slate-500">View only. Machine status is entered manually. Open downtime keeps timing until production recovery is confirmed.</p>
    </main>
  );
}
