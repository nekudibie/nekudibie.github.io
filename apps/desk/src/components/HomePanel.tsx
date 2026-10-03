import { useEffect, useState } from "react";
import { api } from "../api";
import type { Entity } from "../types";
import { ErrorLine, FixtureBadge } from "./Common";

export default function HomePanel({ canControl, onShowCamera }: { canControl: boolean; onShowCamera: (id: string) => void }) {
  const [ents, setEnts] = useState<Entity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api.homeStatus().then((s) => { setEnabled(s.enabled); return s.enabled ? api.entities().then(setEnts) : undefined; }).catch((e) => setError(e.message));
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);

  async function act(e: Entity, action: string, extra: Record<string, unknown> = {}) {
    setBusy(e.entity_id); setError(null);
    try { await api.command(e.entity_id, action, extra); await load(); } catch (err) { setError((err as Error).message); } finally { setBusy(null); }
  }

  if (enabled === false) return <div className="card"><h2>Home</h2><p className="muted">Home control is disabled in configuration (home.provider: disabled).</p></div>;
  const lights = ents.filter((e) => e.capabilities.on_off);
  const scenes = ents.filter((e) => e.domain === "scene");
  const cameras = ents.filter((e) => e.domain === "camera");
  const sensors = ents.filter((e) => e.domain === "sensor" || e.domain === "binary_sensor");
  const fixture = ents.some((e) => e.is_fixture);
  return (
    <div className="grid">
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}><h2>Lights &amp; switches</h2><FixtureBadge show={fixture} /></div>
        <ErrorLine error={error} />
        {lights.length === 0 && <p className="muted">No controllable entities on this client's allowlist.</p>}
        {lights.map((e) => (
          <div className="entity" key={e.entity_id}>
            <div>
              <div>{e.friendly_name}</div>
              <div className="muted" style={{ fontSize: ".85rem" }}>{e.entity_id} · {e.state}{typeof e.attributes.brightness === "number" ? ` · ${Math.round((e.attributes.brightness as number) / 2.55)}%` : ""}</div>
              {e.capabilities.brightness && canControl && (
                <input type="range" min={1} max={100} defaultValue={Math.max(1, Math.round(((e.attributes.brightness as number) || 0) / 2.55))}
                  onMouseUp={(ev) => act(e, "turn_on", { brightness_pct: Number((ev.target as HTMLInputElement).value) })}
                  onTouchEnd={(ev) => act(e, "turn_on", { brightness_pct: Number((ev.target as HTMLInputElement).value) })} aria-label={`${e.friendly_name} brightness`} />
              )}
            </div>
            <button className={`toggle ${e.state === "on" ? "on" : ""}`} disabled={!canControl || busy === e.entity_id} onClick={() => act(e, e.state === "on" ? "turn_off" : "turn_on")}>{e.state === "on" ? "On" : "Off"}</button>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}><h2>Scenes</h2><FixtureBadge show={fixture} /></div>
        <div className="row">{scenes.map((s) => <button key={s.entity_id} disabled={!canControl || busy === s.entity_id} onClick={() => act(s, "activate")}>{s.friendly_name}</button>)}</div>
        {scenes.length === 0 && <p className="muted">No scenes on the allowlist.</p>}
        <h3 style={{ marginTop: 16 }}>Cameras</h3>
        <div className="row">{cameras.map((c) => <button key={c.entity_id} onClick={() => onShowCamera(c.entity_id)}>{c.friendly_name}</button>)}</div>
        {sensors.length > 0 && (<><h3 style={{ marginTop: 16 }}>Sensors</h3>{sensors.map((s) => <div key={s.entity_id} className="entity"><div>{s.friendly_name}</div><div>{s.state} {String(s.attributes.unit || s.attributes.unit_of_measurement || "")}</div></div>)}</>)}
      </div>
    </div>
  );
}
