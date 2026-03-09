
-- 创建 users 表
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    topic_query TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- 创建 daily_reports 表
CREATE TABLE IF NOT EXISTS daily_reports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    report_date DATE NOT NULL,
    theme TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_daily_reports_user_date
ON daily_reports(user_id, report_date DESC, created_at DESC);

-- 插入测试/系统用户数据
INSERT OR IGNORE INTO users (id, username, topic_query, is_active, created_at)
VALUES 
    ('user_1', 'alice', 'cat:cs.AI', 1, datetime('now')),
    ('user_2', 'bob', 'cat:cs.LG', 1, datetime('now')),
    ('user_3', 'charlie', 'all:reinforcement learning', 1, datetime('now')),
    ('smoke_test', 'smoke_test', 'machine learning', 1, datetime('now'));
