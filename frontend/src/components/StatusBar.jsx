export default function StatusBar({ status, message, meta }) {
  const tone = status || 'loading';
  return (
    <section className="status-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className={`status-dot ${tone}`} />
        <span className="status-text">{message}</span>
      </div>
      {meta && <span className="status-meta">{meta}</span>}
    </section>
  );
}
