import { createContext, useContext, useEffect, useState } from "react";
import { api, token } from "./api";

const Auth = createContext(null);
export const useAuth = () => useContext(Auth);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!token.get());
  const logout = () => { token.set(null); setUser(null); };
  useEffect(() => {
    if (token.get()) api.get("/api/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true));
    window.addEventListener("auth-expired", logout);
    return () => window.removeEventListener("auth-expired", logout);
  }, []);
  const accept = (r) => { token.set(r.token); setUser(r.user); };
  const login = async (username, password) => accept(await api.post("/api/auth/login", { username, password }));
  const can = (p) => !!user?.permissions.includes(p);
  return <Auth.Provider value={{ user, ready, login, logout, accept, can }}>{children}</Auth.Provider>;
}
