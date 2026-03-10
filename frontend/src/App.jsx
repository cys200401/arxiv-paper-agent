import { useState, useEffect, useCallback } from 'react';
import StatusBar from './components/StatusBar';
import HeroSection from './components/HeroSection';
import UserTabs from './components/UserTabs';
import PaperCard from './components/PaperCard';
import SettingsPanel from './components/SettingsPanel';
import { getConfig, saveConfig, checkHealth, fetchReports, parseReport, DEFAULT_API_BASE } from './api';

function SkeletonCards() {
  return (
    <div className="skeleton-grid">
      {[1, 2, 3].map(i => (
        <div className="skeleton-card" key={i}>
          <div className="skeleton-line w40 thick" />
          <div className="skeleton-line w80" />
          <div className="skeleton-line w100" />
          <div className="skeleton-line w100" />
          <div className="skeleton-line w60" />
          <div style={{ marginTop: 24 }} />
          <div className="skeleton-line w40" />
          <div className="skeleton-line w80" />
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [token, setToken] = useState('');
  const [userId, setUserId] = useState('user_1');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ tone: 'loading', message: '正在初始化…', meta: '' });

  // Boot: read persisted config & URL params
  useEffect(() => {
    const cfg = getConfig();
    const params = new URLSearchParams(window.location.search);
    setApiBase(params.get('api') || cfg.apiBase || DEFAULT_API_BASE);
    setToken(params.get('token') || cfg.token || '');
    if (params.get('user_id')) setUserId(params.get('user_id'));

    // Strip token from URL for safety
    if (params.has('token')) {
      params.delete('token');
      const next = params.toString() ? `${window.location.pathname}?${params}` : window.location.pathname;
      window.history.replaceState({}, '', next);
    }
  }, []);

  const loadReport = useCallback(async (uid) => {
    const currentToken = token;
    const currentBase = apiBase;

    if (!currentToken) {
      setStatus({ tone: 'error', message: '请先配置 API Token', meta: '在下方输入 API_SECRET_KEY' });
      setReport(null);
      return;
    }

    setLoading(true);
    setStatus({ tone: 'loading', message: '正在获取日报…', meta: `请求 ${uid} 的最新数据` });
    saveConfig({ apiBase: currentBase, token: currentToken });

    try {
      // Health check first
      const health = await checkHealth(currentBase);
      if (health.status !== 'ok') {
        setStatus({ tone: 'error', message: 'API 不可用', meta: health.database || '连接失败' });
        setReport(null);
        setLoading(false);
        return;
      }

      const raw = await fetchReports(uid, 1, { apiBase: currentBase, token: currentToken });
      const parsed = parseReport(raw);

      if (!parsed) {
        setStatus({ tone: 'error', message: '暂无日报数据', meta: `${uid} 还没有生成过日报` });
        setReport(null);
      } else {
        setReport(parsed);
        setStatus({
          tone: 'success',
          message: '已同步最新日报',
          meta: `${parsed.theme} · ${parsed.date} · ${parsed.papers.length} 篇`,
        });
      }
    } catch (err) {
      setStatus({ tone: 'error', message: '加载失败', meta: err.message || '请求出错' });
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [apiBase, token]);

  // Auto-load on token/userId change
  useEffect(() => {
    if (token) loadReport(userId);
  }, [userId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRefresh = () => loadReport(userId);

  const handleUserChange = (uid) => {
    setUserId(uid);
    setReport(null);
  };

  return (
    <main className="shell">
      <StatusBar status={status.tone} message={status.message} meta={status.meta} />

      <HeroSection report={report} />

      <SettingsPanel
        apiBase={apiBase}
        token={token}
        onApiBaseChange={setApiBase}
        onTokenChange={setToken}
        onRefresh={handleRefresh}
        loading={loading}
      />

      <UserTabs active={userId} onChange={handleUserChange} />

      {loading && <SkeletonCards />}

      {!loading && report && report.papers.length > 0 && (
        <section className="papers-grid">
          {report.papers.map(p => (
            <PaperCard key={p.index} paper={p} />
          ))}
        </section>
      )}

      {!loading && report && report.papers.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📄</div>
          <h2>日报内容为空</h2>
          <p>今日的日报已生成，但 top_papers 为空。请检查 Agent 的输出或稍后再试。</p>
        </div>
      )}

      {!loading && !report && status.tone !== 'loading' && (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h2>暂无可展示的日报</h2>
          <p>
            {!token
              ? '请先在上方输入 API Token（即 API_SECRET_KEY），然后点击刷新。'
              : '当前用户没有日报记录。请确认 API 地址和 Token 正确，或等待下一次 Daily Pipeline 运行。'}
          </p>
        </div>
      )}

      <footer className="footer">
        数据来源：
        <a href={apiBase} target="_blank" rel="noopener noreferrer">{apiBase}</a>
        {' · '}arXiv Daily Paper Recommender · Powered by GitHub Actions + Railway
      </footer>
    </main>
  );
}
