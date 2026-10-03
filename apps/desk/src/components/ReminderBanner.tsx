import { useEffect, useState } from "react";
import { api } from "../api";
import type { Reminder } from "../types";

/** Shows delivered reminders until acknowledged. Polls the server: reminders are server state, not a browser timer. */
export default function ReminderBanner({ enabled }: { enabled: boolean }) {
  const [items, setItems] = useState<Reminder[]>([]);
  useEffect(() => {
    if (!enabled) return;
    const load = () => api.pendingReminders().then(setItems).catch(() => undefined);
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [enabled]);
  if (items.length === 0) return null;
  return (
    <div className="banner" role="alert" style={{ borderColor: "var(--info)", background: "#13263a", color: "#cfe6ff" }}>
      {items.map((r) => (
        <div key={r.id} className="row" style={{ justifyContent: "space-between", padding: "4px 0" }}>
          <div><b>⏰ {r.title}</b>{r.body ? <span className="muted"> · {r.body}</span> : null}{r.delivery_count > 1 ? <span className="badge">snoozed ×{r.delivery_count - 1}</span> : null}</div>
          <div className="row">
            <button className="small" onClick={() => api.snoozeReminder(r.id, 10).then(() => setItems((xs) => xs.filter((x) => x.id !== r.id)))}>Snooze 10 min</button>
            <button className="small primary" onClick={() => api.ackReminder(r.id).then(() => setItems((xs) => xs.filter((x) => x.id !== r.id)))}>Done</button>
          </div>
        </div>
      ))}
    </div>
  );
}
