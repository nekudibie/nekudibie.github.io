import { useEffect, useState } from "react";
import { api, getBaseUrl, getToken, saveSettings } from "../api";
import type { Connection } from "../hooks";
import { DepBadge } from "./Common";

export default function SettingsPanel({ conn }: { conn: Connection }) {
  const [url, setUrl] = useState(getBaseUrl());
  const [token, setToken] = useState(getToken());
  const [version, setVersion] = useState<{ version: string; git_sha: string | null; python: string } | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [cfg, setCfg] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { api.version().then(setVersion).catch(() => setVersion(null)); if (conn.phase === "ok") api.settings().then((s) => { setWarnings(s.warnings); setCfg(s.config); }).catch(() => undefined); }, [conn.phase]);

  async function test() {
    saveSettings(url, token); setMsg("Testing…");
    try { const me = await api.me(); setMsg(`Connected as ${me.client_id} (${me.role}).`); conn.refresh(); } catch (e) { setMsg(`Failed: ${(e as Error).message}`); }
  }
  return (
    <div className="grid">
      <div className="card">
        <h2>Connection</h2>
        <p className="muted">The token identifies this screen to the companion API. It is stored only in this browser.</p>
        <label>API address<input value={url} onChange={(e) => setUrl(e.target.value)} /></label>
        <div style={{ height: 8 }} />
        <label>Client token<input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="paste the desk token" /></label>
        <div className="row" style={{ marginTop: 10 }}><button className="primary" onClick={test}>Save &amp; test</button>{msg && <span className="muted">{msg}</span>}</div>
        <h3 style={{ marginTop: 20 }}>Status</h3>
        <div className="row">{conn.deps.map((d) => <DepBadge key={d.name} d={d} />)}</div>
        <ul className="muted" style={{ fontSize: ".9rem" }}>{conn.deps.map((d) => <li key={d.name}><b>{d.name}</b>: {d.detail}{d.latency_ms != null ? ` (${d.latency_ms} ms)` : ""}</li>)}</ul>
        {warnings.length > 0 && <div className="banner">{warnings.map((w) => <div key={w}>⚠ {w}</div>)}</div>}
      </div>
      <div className="card">
        <h2>About</h2>
        <dl className="kv">
          <dt>UI</dt><dd>companion-desk 0.1.0</dd>
          <dt>API</dt><dd>{version ? `${version.version}${version.git_sha ? ` (${version.git_sha})` : ""} · Python ${version.python}` : "unreachable"}</dd>
          <dt>Client</dt><dd>{conn.me ? `${conn.me.client_id} · ${conn.me.role}` : "—"}</dd>
          <dt>Tools</dt><dd>{conn.me?.tools.join(", ") || "—"}</dd>
          <dt>Browser online</dt><dd>{conn.browserOnline ? "yes" : "no"}</dd>
        </dl>
        {cfg && <><h3 style={{ marginTop: 16 }}>Effective configuration (redacted)</h3><pre>{JSON.stringify(cfg, null, 2)}</pre></>}
        <h3>Microphone</h3>
        <p className="muted">Browser microphone capture needs HTTPS or localhost. On the desk Pi, voice uses the native audio client (companion-audio); a software mute there is not a hardware disconnect, and the UI will say which one is active.</p>
      </div>
    </div>
  );
}
