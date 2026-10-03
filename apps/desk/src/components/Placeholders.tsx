export function LearnPanel() {
  return (
    <div className="card">
      <h2>Learning</h2>
      <p className="muted">The Python tutor (course proposals, lessons, exercises, reminders) arrives in Milestone 6. Nothing here is simulated: the page will stay empty until the real tutor service exists.</p>
    </div>
  );
}

export function JobsPanel() {
  return (
    <div className="card">
      <h2>Jobs</h2>
      <p className="muted">Meeting recordings, transcription progress and scheduled reminders will be listed here once the persistent worker ships (Milestone 5/6).</p>
    </div>
  );
}
