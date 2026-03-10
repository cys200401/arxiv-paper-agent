const RAILWAY_API = 'https://web-production-a92e6.up.railway.app';

// In dev mode Vite proxies /api/* and /health to Railway, avoiding CORS.
// In production (or when user overrides), use the full Railway URL.
const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const DEFAULT_API_BASE = isDev ? '' : RAILWAY_API;

function getConfig() {
  const stored = localStorage.getItem('arxiv_api_base');
  return {
    apiBase: stored || DEFAULT_API_BASE,
    token: localStorage.getItem('arxiv_api_token') || '',
  };
}

function saveConfig({ apiBase, token }) {
  if (apiBase) localStorage.setItem('arxiv_api_base', apiBase);
  if (token) localStorage.setItem('arxiv_api_token', token);
}

async function checkHealth(apiBase) {
  const base = (apiBase || getConfig().apiBase).replace(/\/$/, '');
  const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(8000) });
  return res.json();
}

async function fetchReports(userId, limit = 5, overrides = {}) {
  const cfg = { ...getConfig(), ...overrides };
  const base = cfg.apiBase.replace(/\/$/, '');

  if (!cfg.token) throw new Error('请先配置 API Token');

  const res = await fetch(
    `${base}/api/v1/reports?user_id=${encodeURIComponent(userId)}&limit=${limit}`,
    {
      headers: {
        Authorization: `Bearer ${cfg.token}`,
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(15000),
    }
  );

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

function parseReport(raw) {
  const report = raw.reports?.[0];
  if (!report) return null;

  let content = report.content_json;
  if (typeof content === 'string') content = JSON.parse(content);

  return {
    id: report.id,
    userId: report.user_id,
    date: content.date || report.report_date || '--',
    theme: content.theme || report.theme || '未命名主题',
    createdAt: report.created_at,
    papers: (content.top_papers || []).map((p, i) => ({
      index: i + 1,
      title: p.title || '未命名论文',
      originalSummary: p.original_summary || '',
      translation: p.cn_translation || p.original_summary || '暂无摘要翻译。',
      reason: p.recommend_reason || '暂无推荐理由。',
      tags: Array.isArray(p.tech_tags) ? p.tech_tags : [],
    })),
  };
}

export { getConfig, saveConfig, checkHealth, fetchReports, parseReport, DEFAULT_API_BASE };
