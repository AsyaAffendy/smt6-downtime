import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { Account, Users } from "./pages/Account";
import Audit from "./pages/Audit";
import Control from "./pages/Control";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import Login from "./pages/Login";

// The server enforces permissions; this only decides what to show.
function Guard({ need, children }) {
  const { user, ready, can } = useAuth();
  if (!ready) return <p className="p-8 text-slate-400">Loading…</p>;
  if (!user) return <Login />;
  if (need && !can(need)) return <p className="p-8">Your role does not have access to this page.</p>;
  return children;
}

function Header() {
  const { user, logout, can } = useAuth();
  const link = ({ isActive }) => `rounded-lg px-3 py-1.5 text-sm font-semibold ${isActive ? "bg-sky-700" : "text-slate-300 hover:bg-slate-800"}`;
  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900 px-4 py-2">
      <span className="mr-4 text-lg font-black">SMT6 <span className="font-medium text-slate-400">Downtime Monitor</span></span>
      <nav className="flex flex-wrap gap-1">
        <NavLink to="/" className={link} end>Dashboard</NavLink>
        <NavLink to="/control" className={link}>Input / Control</NavLink>
        <NavLink to="/history" className={link}>History &amp; Reports</NavLink>
        {can("audit.view") && <NavLink to="/audit" className={link}>Audit Log</NavLink>}
        {can("users.manage") && <NavLink to="/users" className={link}>Users</NavLink>}
      </nav>
      <span className="flex-1" />
      {user && (
        <>
          <NavLink to="/account" className={link}>{user.name} ({user.role})</NavLink>
          <button className="btn" onClick={logout}>Sign out</button>
        </>
      )}
    </header>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Header />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/control" element={<Guard need="machine.status"><Control /></Guard>} />
          <Route path="/history" element={<Guard need="history.view"><History /></Guard>} />
          <Route path="/audit" element={<Guard need="audit.view"><Audit /></Guard>} />
          <Route path="/users" element={<Guard need="users.manage"><Users /></Guard>} />
          <Route path="/account" element={<Guard><Account /></Guard>} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
