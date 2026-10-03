import { useEffect, useRef, useState } from "react";
import { api, getBaseUrl } from "../api";
import type { CameraView } from "../types";
import { ErrorLine, FixtureBadge } from "./Common";

type Mode = "stream" | "snapshot";

export default function CameraPanel({ selected, setSelected }: { selected: string | null; setSelected: (id: string | null) => void }) {
  const [cams, setCams] = useState<CameraView[]>([]);
  const [img, setImg] = useState<string | null>(null);
  const [streamSrc, setStreamSrc] = useState<string | null>(null);
  const [fixture, setFixture] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [live, setLive] = useState(true);
  const [mode, setMode] = useState<Mode>("stream");
  const prev = useRef<string | null>(null);

  useEffect(() => { api.cameras().then((c) => { setCams(c); if (!selected && c[0]) setSelected(c[0].entity_id); }).catch((e) => setError(e.message)); }, []); // eslint-disable-line

  const cam = cams.find((c) => c.entity_id === selected);
  const canStream = !!cam && cam.stream_kind === "mjpeg";
  const effectiveMode: Mode = canStream && mode === "stream" ? "stream" : "snapshot";

  // MJPEG stream through a short-lived ticket (the client token never goes in a URL).
  useEffect(() => {
    if (!selected || !live || effectiveMode !== "stream") { setStreamSrc(null); return; }
    let stop = false;
    const issue = async () => {
      try {
        const t = await api.streamTicket(selected);
        if (stop) return;
        setStreamSrc(`${getBaseUrl()}${t.stream_url}?ticket=${encodeURIComponent(t.ticket)}`);
        setFixture(false); setError(null); setUpdated(new Date());
      } catch (e) { if (!stop) { setError((e as Error).message); setMode("snapshot"); } }
    };
    issue();
    const t = setInterval(issue, 50000);
    return () => { stop = true; clearInterval(t); };
  }, [selected, live, effectiveMode]);

  // Snapshot polling (fixture cameras and fallback).
  useEffect(() => {
    if (!selected || effectiveMode !== "snapshot") return;
    let stop = false;
    const tick = async () => {
      try {
        const { url, fixture } = await api.snapshotBlob(selected);
        if (stop) { URL.revokeObjectURL(url); return; }
        if (prev.current) URL.revokeObjectURL(prev.current);
        prev.current = url; setImg(url); setFixture(fixture); setUpdated(new Date()); setError(null);
      } catch (e) { if (!stop) setError((e as Error).message); }
    };
    tick();
    const t = live ? setInterval(tick, 3000) : undefined;
    return () => { stop = true; if (t) clearInterval(t); };
  }, [selected, live, effectiveMode]);

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Camera</h2>
        <div className="row">{cams.map((c) => <button key={c.entity_id} className={`small ${c.entity_id === selected ? "primary" : ""}`} onClick={() => setSelected(c.entity_id)}>{c.friendly_name}</button>)}</div>
      </div>
      <ErrorLine error={error} />
      <div className="camera-frame">
        {effectiveMode === "stream" && streamSrc
          ? <img src={streamSrc} alt={cam?.friendly_name || "camera"} onError={() => { setError("Stream failed; showing snapshots."); setMode("snapshot"); }} />
          : img ? <img src={img} alt={cam?.friendly_name || "camera"} /> : <span className="muted">No image yet</span>}
        <div className="overlay row">
          <FixtureBadge show={fixture} text="Fixture placeholder · not a live feed" />
          {!fixture && cam && <span className="badge info">{effectiveMode === "stream" ? "live MJPEG via Home Assistant" : "snapshot refresh every 3 s"}</span>}
        </div>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="small" onClick={() => setLive(!live)}>{live ? "Pause" : "Resume"}</button>
        {canStream && <button className="small" onClick={() => setMode(mode === "stream" ? "snapshot" : "stream")}>{mode === "stream" ? "Use snapshots" : "Use stream"}</button>}
        <span className="muted">{updated ? `updated ${updated.toLocaleTimeString("en-GB")}` : ""}</span>
        {cam?.note && <span className="muted">{cam.note}</span>}
      </div>
    </div>
  );
}
