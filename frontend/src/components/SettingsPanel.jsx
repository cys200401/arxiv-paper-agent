import { DEFAULT_API_BASE } from '../api';

export default function SettingsPanel({ apiBase, token, onApiBaseChange, onTokenChange, onRefresh, loading }) {
  return (
    <section className="settings">
      <div className="field">
        <label htmlFor="api-base">API Base</label>
        <input
          id="api-base"
          type="text"
          value={apiBase}
          onChange={e => onApiBaseChange(e.target.value)}
          placeholder={DEFAULT_API_BASE}
        />
      </div>
      <div className="field">
        <label htmlFor="api-token">API Token</label>
        <input
          id="api-token"
          type="password"
          value={token}
          onChange={e => onTokenChange(e.target.value)}
          placeholder="输入 API_SECRET_KEY"
        />
      </div>
      <div className="field" style={{ display: 'flex', alignItems: 'flex-end' }}>
        <button
          className="btn-primary"
          onClick={onRefresh}
          disabled={loading}
          style={{ width: '100%' }}
        >
          {loading ? '加载中…' : '🔄 刷新日报'}
        </button>
      </div>
    </section>
  );
}
