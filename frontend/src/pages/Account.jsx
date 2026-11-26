import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, Form } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

const ROLES = ["operator", "technician", "supervisor", "admin"];
const Password = ({ name, label }) => (
  <Field label={label}><input type="password" name={name} minLength={10} maxLength={72} required autoComplete="new-password" className="input" /></Field>
);

export function Account() {
  const { accept, user } = useAuth();
  const [saved, setSaved] = useState(false);
  return (
    <main className="mx-auto w-full max-w-md space-y-3 p-4">
      <h1 className="text-xl font-bold">{user.name} · {user.role}</h1>
      {saved && <p className="text-emerald-400">Password changed.</p>}
      <Form className="panel p-4" submit="Change password" onSubmit={async (d) => { setSaved(false); accept(await api.post("/api/auth/password", d)); setSaved(true); }}>
        <Field label="Current password"><input type="password" name="current_password" required autoComplete="current-password" className="input" /></Field>
        <Password name="new_password" label="New password (10+ characters)" />
      </Form>
    </main>
  );
}

export function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/api/users").then(setUsers).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const update = (id, body) => { setError(""); return api.patch(`/api/users/${id}`, body).then(load).catch((e) => setError(e.message)); };
  return (
    <main className="mx-auto w-full max-w-5xl space-y-4 p-4">
      <ErrorBox message={error} />
      <section className="panel overflow-x-auto p-2">
        <table className="w-full">
          <thead><tr>{["Username", "Name", "Role", "Access", "Reset password"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td className="td font-mono">{u.username}</td>
                <td className="td">{u.full_name}</td>
                <td className="td">
                  <select className="input" value={u.role} disabled={u.id === me.id} onChange={(e) => update(u.id, { role: e.target.value })}>
                    {ROLES.map((r) => <option key={r}>{r}</option>)}
                  </select>
                </td>
                <td className="td"><button className="btn" disabled={u.id === me.id} onClick={() => update(u.id, { active: !u.active })}>{u.active ? "Deactivate" : "Reactivate"}</button></td>
                <td className="td">
                  {u.id !== me.id && (
                    <Form className="flex flex-wrap items-center gap-2 !space-y-0" submit="Reset" tone="" onSubmit={async (d) => { await api.patch(`/api/users/${u.id}`, d); }}>
                      <input type="password" name="password" minLength={10} maxLength={72} required autoComplete="new-password" placeholder="New password" aria-label={`New password for ${u.username}`} className="input !w-44" />
                    </Form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <Form className="panel p-4" submit="Create user" onSubmit={async (d) => { await api.post("/api/users", d); await load(); }}>
        <h2 className="font-bold">New user</h2>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Username"><input name="username" required pattern="[A-Za-z0-9._\-]{3,40}" className="input" /></Field>
          <Field label="Full name"><input name="full_name" required className="input" /></Field>
          <Field label="Role"><select name="role" className="input">{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <Password name="password" label="Password (10+)" />
        </div>
      </Form>
    </main>
  );
}
