function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export default function PaperCard({ paper }) {
  return (
    <article className="paper-card" style={{ animationDelay: `${(paper.index - 1) * 80}ms` }}>
      <span className="paper-index">{paper.index}</span>
      <h2>{escapeHtml(paper.title)}</h2>

      <section>
        <span className="section-label">中文摘要</span>
        <p className="paper-translation">{paper.translation}</p>
      </section>

      <section>
        <span className="section-label">推荐理由</span>
        <p className="paper-reason">{paper.reason}</p>
      </section>

      {paper.tags.length > 0 && (
        <div className="tag-row">
          {paper.tags.map((tag, i) => (
            <span className="tag" key={i}>{tag}</span>
          ))}
        </div>
      )}
    </article>
  );
}
