import { useEffect, useState } from "react";
import { api } from "../api";
import type { AttemptResult, LessonSummary, LessonView, Proposal, Schedule } from "../types";
import { ErrorLine, fmtTime } from "./Common";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function LearnPanel({ intent }: { intent?: { kind: string; lesson_id?: string } | null }) {
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [summary, setSummary] = useState<{ lessons: number; mastered: number; needs_review: string[]; weak_topics: string[]; attempts: number } | null>(null);
  const [course, setCourse] = useState<{ title: string; description: string } | null>(null);
  const [lesson, setLesson] = useState<LessonView | null>(null);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState<Record<string, string>>({});
  const [output, setOutput] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, AttemptResult>>({});
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [goal, setGoal] = useState("");
  const [time, setTime] = useState("19:30");
  const [plan, setPlan] = useState<Schedule[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api.tutorCourse().then((c) => { setLessons(c.lessons); setSummary(c.summary); setCourse(c.course); }).catch((e) => setError(e.message));
    api.tutorPlan().then(setPlan).catch(() => setPlan([]));
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (intent?.kind === "open_lesson" && intent.lesson_id) openLesson(intent.lesson_id);
    if (intent?.kind === "choose_plan") api.tutorPropose(goal, time).then((p) => setProposals(p.proposals)).catch((e) => setError(e.message));
  }, [intent]); // eslint-disable-line

  function openLesson(id: string) { api.tutorLesson(id).then((l) => { setLesson(l); setReason(""); setResults({}); }).catch((e) => setError(e.message)); }
  function openNext() { api.tutorNext().then((n) => { setLesson(n.lesson); setReason(n.reason); setResults({}); }).catch((e) => setError(e.message)); }
  async function submit(exId: string) {
    if (!lesson) return;
    try {
      const r = await api.tutorAttempt(lesson.id, exId, code[exId] ?? lesson.exercises.find((e) => e.id === exId)?.starter ?? "", output[exId] ?? null);
      setResults((x) => ({ ...x, [exId]: r })); load();
    } catch (e) { setError((e as Error).message); }
  }
  async function accept(id: string) {
    try { await api.tutorAccept(id, time); setProposals(null); load(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>{course?.title || "Learning"}</h2>
        <p className="muted">{course?.description}</p>
        <ErrorLine error={error} />
        {summary && <p><span className="badge ok">{summary.mastered}/{summary.lessons} mastered</span> <span className="badge">{summary.attempts} attempts</span>{summary.weak_topics.length > 0 && <span className="badge fixture">revisit: {summary.weak_topics.join(", ")}</span>}</p>}
        <div className="row"><button className="primary" onClick={openNext}>Next lesson for me</button></div>
        <div className="list" style={{ marginTop: 10 }}>
          {lessons.map((l, i) => <div key={l.id} className="item" onClick={() => openLesson(l.id)}><b>{i + 1}. {l.title}</b> <span className={`badge ${l.status === "mastered" ? "ok" : l.status === "needs_review" ? "fixture" : ""}`}>{l.status.replace("_", " ")}</span> <span className="muted" style={{ fontSize: ".8rem" }}>{l.minutes} min · {l.exercises} exercise{l.exercises !== 1 ? "s" : ""}</span></div>)}
        </div>
        <h3 style={{ marginTop: 18 }}>Schedule</h3>
        {plan.length > 0 ? plan.map((s) => <div key={s.id} className="item" style={{ cursor: "default" }}>{s.title} · {(s.rule.days || []).map((d) => DAYS[d]).join("/")} at {s.rule.time_local} ({s.timezone}) · next {s.next_run_at ? fmtTime(s.next_run_at) : "—"} <span className="badge">{s.status}</span>
          <div className="row" style={{ marginTop: 4 }}>{s.status === "active" ? <button className="small" onClick={() => api.scheduleAction(s.id, "pause").then(load)}>Pause</button> : <button className="small" onClick={() => api.scheduleAction(s.id, "resume").then(load)}>Resume</button>}<button className="small danger" onClick={() => api.scheduleAction(s.id, "cancel").then(load)}>Cancel</button></div></div>)
          : <p className="muted">No lesson schedule yet. Reminders are only created when you accept a plan.</p>}
        <div className="row" style={{ marginTop: 8 }}>
          <input placeholder="Your goal (optional), e.g. automate my notes" value={goal} onChange={(e) => setGoal(e.target.value)} style={{ flex: 1 }} />
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} style={{ width: 130 }} />
          <button onClick={() => api.tutorPropose(goal, time).then((p) => setProposals(p.proposals)).catch((e) => setError(e.message))}>Propose a plan</button>
        </div>
        {proposals && (
          <div className="list" style={{ marginTop: 8 }}>
            {proposals.map((p) => <div key={p.id} className="item" style={{ cursor: "default" }}><b>{p.title}</b><div className="muted" style={{ fontSize: ".85rem" }}>{p.description}</div><button className="small primary" style={{ marginTop: 4 }} onClick={() => accept(p.id)}>Choose this plan</button></div>)}
            <p className="muted" style={{ fontSize: ".85rem" }}>Nothing is scheduled until you choose. Reminders follow Europe/London time, including the clock changes.</p>
          </div>
        )}
      </div>
      <div className="card">
        {lesson ? (
          <>
            <div className="row" style={{ justifyContent: "space-between" }}><h2>{lesson.title}</h2><button className="small" onClick={() => setLesson(null)}>Back</button></div>
            {reason && <p className="muted">{reason}</p>}
            <h3>Objectives</h3><ul>{lesson.objectives.map((o) => <li key={o}>{o}</li>)}</ul>
            <h3>Explanation</h3><p style={{ whiteSpace: "pre-wrap" }}>{lesson.explanation}</p>
            <h3>Examples (verified output)</h3>
            {lesson.examples.map((ex, i) => <div key={i} style={{ marginBottom: 10 }}><pre>{ex.code}</pre><div className="muted">prints:</div><pre>{ex.output}</pre>{ex.note && <div className="muted">{ex.note}</div>}</div>)}
            <h3>Exercises</h3>
            {lesson.exercises.map((ex) => {
              const r = results[ex.id];
              return (
                <div key={ex.id} className="item" style={{ cursor: "default", marginBottom: 10 }}>
                  <p>{ex.prompt}</p>
                  <textarea value={code[ex.id] ?? ex.starter} onChange={(e) => setCode((c) => ({ ...c, [ex.id]: e.target.value }))} spellCheck={false} style={{ fontFamily: "ui-monospace, monospace", minHeight: 120 }} />
                  {ex.needs_output && <input placeholder="Paste what your code printed when you ran it (python3 yourfile.py)" value={output[ex.id] ?? ""} onChange={(e) => setOutput((o) => ({ ...o, [ex.id]: e.target.value }))} style={{ marginTop: 6 }} />}
                  <div className="row" style={{ marginTop: 6 }}><button className="primary small" onClick={() => submit(ex.id)}>Check my code</button><span className="muted" style={{ fontSize: ".8rem" }}>Static check: your code is read, not run here. Run it yourself in a terminal.</span></div>
                  {r && (
                    <div style={{ marginTop: 8 }}>
                      <span className={`badge ${r.result.passed ? "ok" : "bad"}`}>{r.result.passed ? "passed" : "not yet"} · {Math.round(r.result.score * 100)}%</span> <span className="badge">{r.progress.status.replace("_", " ")}</span>
                      <ul>{r.result.feedback.map((f, i) => <li key={i}>{f}</li>)}</ul>
                      {r.hint && <div className="banner">Hint: {r.hint}</div>}
                      {r.solution_notes && <div className="muted">{r.solution_notes}</div>}
                    </div>
                  )}
                </div>
              );
            })}
            {lesson.references.length > 0 && <><h3>Read more</h3><ul>{lesson.references.map((u) => <li key={u}><a href={u} target="_blank" rel="noreferrer">{u}</a></li>)}</ul></>}
            {lesson.next_steps && <p className="muted">{lesson.next_steps}</p>}
          </>
        ) : <><h2>Lesson</h2><p className="muted">Pick a lesson, or press “Next lesson for me” and the tutor chooses based on your attempts (review first when something needs another go).</p></>}
      </div>
    </div>
  );
}
