const timeOf = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });

export default function ActivityLog({ messages }) {
  const newestFirst = messages.slice().reverse();
  return (
    <section className="block log-block" aria-labelledby="h-log">
      <h2 id="h-log">Activity</h2>
      <ol className="log">
        {newestFirst.length === 0 && <li>Nothing yet.</li>}
        {newestFirst.map((m, i) => (
          <li key={`${m.t}-${i}`}>
            <time>{timeOf(m.t)}</time>
            <span>{m.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
