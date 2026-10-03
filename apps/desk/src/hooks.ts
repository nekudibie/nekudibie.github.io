import { useEffect, useRef, useState } from "react";
import { api, ApiError, getToken } from "./api";
import type { Dependency, Me } from "./types";

export function useClock(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), intervalMs); return () => clearInterval(t); }, [intervalMs]);
  return now;
}

export interface Connection {
  phase: "unconfigured" | "checking" | "ok" | "unauthorised" | "unreachable";
  me: Me | null;
  deps: Dependency[];
  llmOffline: boolean;
  refresh: () => void;
  browserOnline: boolean;
}

export function useConnection(pollMs = 15000): Connection {
  const [phase, setPhase] = useState<Connection["phase"]>(getToken() ? "checking" : "unconfigured");
  const [me, setMe] = useState<Me | null>(null);
  const [deps, setDeps] = useState<Dependency[]>([]);
  const [tick, setTick] = useState(0);
  const [browserOnline, setBrowserOnline] = useState(navigator.onLine);
  const alive = useRef(true);

  useEffect(() => {
    const on = () => setBrowserOnline(true), off = () => setBrowserOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  useEffect(() => {
    alive.current = true;
    const run = async () => {
      if (!getToken()) { setPhase("unconfigured"); setMe(null); return; }
      try {
        const m = await api.me();
        if (!alive.current) return;
        setMe(m); setPhase("ok");
        try { const s = await api.status(); if (alive.current) setDeps(s.dependencies); } catch { /* status is best-effort */ }
      } catch (e) {
        if (!alive.current) return;
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) setPhase("unauthorised");
        else setPhase("unreachable");
      }
    };
    run();
    const t = setInterval(run, pollMs);
    return () => { alive.current = false; clearInterval(t); };
  }, [tick, pollMs]);

  const llm = deps.find((d) => d.name === "llm");
  return { phase, me, deps, llmOffline: !!llm && llm.status === "down", refresh: () => setTick((x) => x + 1), browserOnline };
}

export function useLocalState<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => { try { const raw = localStorage.getItem(key); return raw ? (JSON.parse(raw) as T) : initial; } catch { return initial; } });
  return [v, (nv: T) => { setV(nv); try { localStorage.setItem(key, JSON.stringify(nv)); } catch { /* ignore */ } }];
}
