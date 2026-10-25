export default function KeyPrompt({ keys, label, onClick, disabled }) {
  return (
    <button className="key-prompt" onClick={onClick} disabled={disabled}>
      <span className="press">Press</span>
      {keys.map((k, i) => (
        <span key={k} className="keys">
          {i > 0 && <span className="or">or</span>}
          <kbd className="cap">{k}</kbd>
        </span>
      ))}
      <span className="what">{label}</span>
    </button>
  );
}
