import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorLine, FixtureBadge, fmtTime } from "./Common";

type Weather = Awaited<ReturnType<typeof api.weather>>["data"];
type DeckRow = Awaited<ReturnType<typeof api.decks>>[number];
type Check = Awaited<ReturnType<typeof api.checkDeckCard>>["data"];
type Mail = Awaited<ReturnType<typeof api.emailSearch>>;

export default function ToolsPanel({ can }: { can: (p: string) => boolean }) {
  const [weather, setWeather] = useState<Weather | null>(null);
  const [expr, setExpr] = useState("2*x + 3 = 11"); const [task, setTask] = useState("evaluate"); const [maths, setMaths] = useState<string[] | null>(null);
  const [decks, setDecks] = useState<DeckRow[]>([]); const [deckName, setDeckName] = useState(""); const [deckFormat, setDeckFormat] = useState("commander"); const [decklist, setDecklist] = useState("");
  const [card, setCard] = useState(""); const [check, setCheck] = useState<Check | null>(null); const [selDeck, setSelDeck] = useState<string>("");
  const [mailQ, setMailQ] = useState(""); const [mail, setMail] = useState<Mail | null>(null); const [mailStatus, setMailStatus] = useState<Awaited<ReturnType<typeof api.emailStatus>> | null>(null);
  const [orders, setOrders] = useState<{ merchant: string; order_ref: string; status: string; amount?: number | null; currency?: string | null; items: { name?: string }[]; updated_at: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [robot, setRobot] = useState<Awaited<ReturnType<typeof api.robotStatus>> | null | "off">(null);

  useEffect(() => {
    if (can("robot.status")) {
      const load = () => api.robotStatus().then(setRobot).catch(() => setRobot("off"));
      load(); const t = setInterval(load, 3000); return () => clearInterval(t);
    }
  }, []); // eslint-disable-line
  useEffect(() => {
    if (can("weather.read")) api.weather("week").then((w) => setWeather(w.data)).catch(() => setWeather(null));
    if (can("mtg.read")) api.decks().then(setDecks).catch(() => setDecks([]));
    if (can("email.read")) { api.emailStatus().then(setMailStatus).catch(() => undefined); (api.orders(false) as Promise<typeof orders>).then(setOrders).catch(() => undefined); }
  }, []); // eslint-disable-line

  return (
    <div className="grid">
      {can("weather.read") && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}><h2>Weather</h2>{weather && <FixtureBadge show={weather.is_fixture} text="Fixture forecast · invented numbers" />}</div>
          {!weather && <p className="muted">Weather is off or unavailable (set weather.provider and a location).</p>}
          {weather && (<>
            <p className="muted">{weather.location} · fetched {fmtTime(weather.fetched_at)}{weather.is_stale && <span className="badge bad" style={{ marginLeft: 6 }}>stale: {weather.stale_reason}</span>}</p>
            <div className="list">{weather.days.map((d) => <div key={d.date} className="item" style={{ cursor: "default" }}><b>{new Date(d.date).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}</b> · {d.description} · {d.temp_min_c ?? "?"}–{d.temp_max_c ?? "?"} °C{d.precipitation_probability_pct != null ? ` · ${d.precipitation_probability_pct}% rain` : ""}</div>)}</div>
            <p className="muted" style={{ fontSize: ".8rem" }}>{weather.is_fixture ? weather.attribution : <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com</a>}</p>
          </>)}
        </div>
      )}
      {can("maths.use") && (
        <div className="card">
          <h2>Maths</h2>
          <p className="muted">Worked out symbolically with SymPy, never by the language model. Use ^ for powers and = for an equation.</p>
          <div className="row"><input value={expr} onChange={(e) => setExpr(e.target.value)} style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && api.maths(expr, task).then((m) => setMaths([m.data.explanation, ...m.data.steps, m.data.method])).catch((er) => setMaths([er.message]))} />
            <select value={task} onChange={(e) => setTask(e.target.value)} style={{ minHeight: 48, borderRadius: 12, padding: "0 10px", background: "var(--panel-2)", border: "1px solid var(--line)" }}>{["evaluate", "solve", "simplify", "differentiate", "integrate"].map((t) => <option key={t}>{t}</option>)}</select>
            <button className="primary" onClick={() => api.maths(expr, task).then((m) => setMaths([m.data.explanation, ...m.data.steps, m.data.method])).catch((er) => setMaths([er.message]))}>Go</button></div>
          {maths && <ul>{maths.map((l, i) => <li key={i} className={i === maths.length - 1 ? "muted" : ""}>{l}</li>)}</ul>}
        </div>
      )}
      {can("mtg.read") && (
        <div className="card">
          <h2>Magic decks</h2>
          <ErrorLine error={error} />
          {decks.length === 0 ? <p className="muted">No saved decks yet.</p> : (
            <div className="row" style={{ marginBottom: 8 }}>
              <select value={selDeck} onChange={(e) => setSelDeck(e.target.value)} style={{ minHeight: 44, borderRadius: 12, padding: "0 10px", background: "var(--panel-2)", border: "1px solid var(--line)" }}><option value="">choose a deck…</option>{decks.map((d) => <option key={d.document_id} value={d.document_id}>{d.name} ({d.format}{d.commander ? `, ${d.commander}` : ""}, {d.main_count} cards)</option>)}</select>
              <input placeholder="Card name" value={card} onChange={(e) => setCard(e.target.value)} style={{ flex: 1 }} />
              <button className="primary" disabled={!selDeck || !card} onClick={() => api.checkDeckCard(selDeck, card).then((r) => setCheck(r.data)).catch((er) => setError(er.message))}>Check</button>
            </div>
          )}
          {check && (
            <div className="item" style={{ cursor: "default" }}>
              <div><b>{check.card?.name || card}</b> <span className={`badge ${check.legal ? "ok" : check.legal === false ? "bad" : "fixture"}`}>{check.legal ? "legal" : check.legal === false ? "not legal" : "unresolved"}</span> <FixtureBadge show={check.is_fixture} text="Fixture card data" /></div>
              {check.ambiguous.length > 0 && <div className="muted">Did you mean: {check.ambiguous.join(", ")}?</div>}
              <ul>{check.findings.map((f, i) => <li key={i}>{f.ok ? "✓" : "✗"} {f.detail}{f.rule ? <span className="muted"> (rule {f.rule}: {check.rules[f.rule]})</span> : null}</li>)}</ul>
              <div className="muted" style={{ fontSize: ".85rem" }}>{check.note}</div>
            </div>
          )}
          {can("memory.write") && (<>
            <h3 style={{ marginTop: 14 }}>Save a deck</h3>
            <div className="row"><input placeholder="Deck name" value={deckName} onChange={(e) => setDeckName(e.target.value)} /><input placeholder="format (commander, modern…)" value={deckFormat} onChange={(e) => setDeckFormat(e.target.value)} style={{ width: 200 }} /></div>
            <textarea placeholder={"// Commander\n1 Thassa, Deep-Dwelling\n// Main\n1 Counterspell\n30 Island\nCUSTOM: My Card | rules text"} value={decklist} onChange={(e) => setDecklist(e.target.value)} style={{ marginTop: 6, fontFamily: "ui-monospace, monospace" }} />
            <button className="small primary" style={{ marginTop: 6 }} disabled={!deckName || !decklist} onClick={() => api.importDeck(deckName, deckFormat, decklist).then(() => { setDecklist(""); api.decks().then(setDecks); }).catch((er) => setError(er.message))}>Save deck</button>
          </>)}
        </div>
      )}
      {can("robot.status") && robot !== "off" && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}><h2>Robot body</h2><span className="badge fixture">⚠ {robot?.mode === "simulated" ? "simulated · no motors" : robot?.mode}</span></div>
          {robot ? (<>
            <p><span className={`badge ${robot.state === "idle" ? "ok" : robot.state.startsWith("stopped") || robot.state === "estop" ? "bad" : "info"}`}>{robot.state.replace("_", " ")}</span> <span className="muted">{robot.reason}</span></p>
            <dl className="kv"><dt>Pose</dt><dd>x {robot.pose.x_m.toFixed(2)} m · y {robot.pose.y_m.toFixed(2)} m · {robot.pose.theta_deg.toFixed(0)}°</dd><dt>Link</dt><dd>{robot.sensors.link_ok ? "ok" : "lost"}</dd><dt>Bumper / cliff</dt><dd>{robot.sensors.bumper_front ? "pressed" : "clear"} / {robot.sensors.cliff_front ? "detected" : "clear"}</dd><dt>Battery</dt><dd>{robot.sensors.battery_pct.toFixed(1)}%</dd><dt>Limits</dt><dd>{robot.limits.max_linear_mps} m/s · {robot.limits.max_angular_rps} rad/s · watchdog {robot.limits.watchdog_timeout_s}s</dd></dl>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="danger" onClick={() => api.robotAction("stop").then(() => api.robotStatus().then(setRobot))}>■ Stop</button>
              <button className="danger" onClick={() => api.robotAction("estop").then(() => api.robotStatus().then(setRobot))}>E-STOP</button>
              {robot.estop_latched && can("robot.command") && <button onClick={() => api.robotAction("reset").then(() => api.robotStatus().then(setRobot)).catch((e) => setError(e.message))}>Reset e-stop</button>}
              {can("robot.command") && ["left", "centre", "right"].map((d) => <button key={d} className="small" onClick={() => api.robotLook(d).then(() => api.robotStatus().then(setRobot)).catch((e) => setError(e.message))}>look {d}</button>)}
            </div>
            <p className="muted" style={{ fontSize: ".8rem" }}>{robot.note}</p>
          </>) : <p className="muted">Loading…</p>}
        </div>
      )}
      {can("email.read") && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}><h2>Email &amp; orders</h2>{mailStatus && <span className={`badge ${mailStatus.enabled ? (mailStatus.is_fixture ? "fixture" : "ok") : ""}`}>{mailStatus.enabled ? `${mailStatus.provider}${mailStatus.is_fixture ? " · fixture mailbox" : ""} · read-only` : "disabled"}</span>}</div>
          {mailStatus?.health && <p className="muted" style={{ fontSize: ".85rem" }}>{mailStatus.health.detail}</p>}
          <div className="row"><input placeholder="Search emails (read-only)…" value={mailQ} onChange={(e) => setMailQ(e.target.value)} style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && api.emailSearch(mailQ).then(setMail).catch((er) => setError(er.message))} /><button onClick={() => api.emailSearch(mailQ).then(setMail).catch((er) => setError(er.message))}>Search</button></div>
          {mail && <div className="list" style={{ marginTop: 8 }}>{mail.messages.length === 0 && <p className="muted">No matches.</p>}{mail.messages.map((m) => <div key={m.id} className="item" style={{ cursor: "default" }}><b>{m.subject || "(no subject)"}</b><div className="muted" style={{ fontSize: ".85rem" }}>{m.sender} · {m.date ? fmtTime(m.date) : ""}</div><div style={{ fontSize: ".9rem" }}>{m.snippet}</div>{m.link && <a href={m.link} target="_blank" rel="noreferrer">open</a>}</div>)}</div>}
          <h3 style={{ marginTop: 14 }}>Purchases</h3>
          <button className="small" onClick={() => (api.orders(true) as Promise<unknown>).then(() => (api.orders(false) as Promise<typeof orders>).then(setOrders)).catch((er) => setError(er.message))}>Sync from email</button>
          <div className="list" style={{ marginTop: 8 }}>{orders.length === 0 && <p className="muted">No purchases recorded. A confirmation email is not proof of delivery; statuses follow the latest email seen.</p>}{orders.map((o) => <div key={o.order_ref} className="item" style={{ cursor: "default" }}><b>{o.merchant}</b> {o.order_ref} <span className={`badge ${o.status === "delivered" ? "ok" : o.status === "refunded" || o.status === "cancelled" ? "bad" : "info"}`}>{o.status}</span><div className="muted" style={{ fontSize: ".85rem" }}>{o.items.map((i) => i.name).filter(Boolean).join(", ") || "items not listed"}{o.amount != null ? ` · ${o.currency || ""} ${o.amount.toFixed(2)}` : ""} · {fmtTime(o.updated_at)}</div></div>)}</div>
        </div>
      )}
    </div>
  );
}
