export default function HeroSection({ report }) {
  const date = report?.date || '--';
  const theme = report?.theme || '--';
  const count = report?.papers?.length ?? '--';
  const userId = report?.userId || '--';
  const desc = report
    ? `围绕「${theme}」精选 ${count} 篇论文，用更适合中文读者的节奏呈现重点摘要、推荐理由与技术标签。`
    : '汇集当天最值得读的论文摘要、中文翻译与推荐理由，适合晨间浏览、午间快速筛选和晚间沉浸式补课。';

  return (
    <section className="hero">
      <span className="hero-eyebrow">✦ Daily Research Pulse</span>
      <div className="hero-grid">
        <div>
          <h1>每日论文速递</h1>
          <p className="hero-desc">{desc}</p>
        </div>
        <aside className="stats-panel">
          <p className="stats-label">Report Snapshot</p>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-item-label">日期</span>
              <span className="stat-item-value">{date}</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">主题</span>
              <span className="stat-item-value">{theme}</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">论文数</span>
              <span className="stat-item-value">{typeof count === 'number' ? `${count} 篇` : count}</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">读者</span>
              <span className="stat-item-value">{userId}</span>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
