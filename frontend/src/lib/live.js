import { useEffect, useState } from "react";
import { setZone } from "./time";

// Same rule as api.js: same-origin unless VITE_API_BASE points elsewhere.
const WS_URL = import.meta.env.VITE_API_BASE
  ? `${import.meta.env.VITE_API_BASE.replace(/^http/, "ws")}/ws/dashboard`
  : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/dashboard`;

/** Live dashboard feed: reconnects automatically and flags stale data. */
export function useLive() {
  const [state, setState] = useState({ data: null, offset: 0, connected: false, received: 0 });
  useEffect(() => {
    let socket, retry, delay = 1000, stopped = false, last = Date.now();
    const reconnect = () => {
      if (stopped) return;
      setState((s) => ({ ...s, connected: false }));
      retry = setTimeout(connect, delay);
      delay = Math.min(delay * 2, 15000);
    };
    const discard = () => {
      socket.onmessage = null;
      socket.onclose = null;
      socket.close();
    };
    const connect = () => {
      retry = null;
      last = Date.now();
      socket = new WebSocket(WS_URL);
      socket.onmessage = (e) => {
        const data = JSON.parse(e.data);
        last = Date.now();
        delay = 1000;
        setZone(data.timezone);
        setState({ data, offset: Date.parse(data.server_time) - last, connected: true, received: last });
      };
      socket.onclose = reconnect;
    };
    connect();
    // The server sends at least every 15 s. Silence means the link is dead.
    const watchdog = setInterval(() => {
      if (!retry && Date.now() - last > 40000) {
        discard();
        reconnect();
      }
    }, 5000);
    return () => { stopped = true; clearTimeout(retry); clearInterval(watchdog); discard(); };
  }, []);
  return state;
}

export function useNow() {
  const [t, setT] = useState(Date.now());
  useEffect(() => { const i = setInterval(() => setT(Date.now()), 1000); return () => clearInterval(i); }, []);
  return t;
}
