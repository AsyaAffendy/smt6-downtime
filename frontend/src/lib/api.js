// Same-origin by default (local dev, or frontend+backend served from one address).
// Set VITE_API_BASE at build time (e.g. on Railway) to call a backend on a different URL.
const API_BASE = import.meta.env.VITE_API_BASE || "";

const KEY = "smt6.token";
export const token = {
  get: () => { try { return sessionStorage.getItem(KEY); } catch { return null; } },
  set: (v) => { try { v ? sessionStorage.setItem(KEY, v) : sessionStorage.removeItem(KEY); } catch { /* ignore */ } },
};

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (token.get()) headers.Authorization = `Bearer ${token.get()}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new Error("Cannot reach the server. Check the network and try again.");
  }
  if (!res.ok) {
    if (res.status === 401 && !path.endsWith("/login")) window.dispatchEvent(new Event("auth-expired"));
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ")
      : data.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res;
}

export const api = {
  get: (p) => request(p).then((r) => r.json()),
  post: (p, body = {}) => request(p, { method: "POST", body }).then((r) => r.json()),
  patch: (p, body) => request(p, { method: "PATCH", body }).then((r) => r.json()),
  async download(path, filename) {
    const blob = await (await request(path)).blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  },
};

export const query = (params) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();
