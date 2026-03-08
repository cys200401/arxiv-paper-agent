
-- 创建 users 表
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    topic_query TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

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

-- 插入三条测试用户数据
INSERT INTO users (id, username, topic_query, is_active, created_at)
VALUES 
    ('u001', 'alice', 'AI 与信号处理在通信工程的应用', 1, datetime('now')),
    ('u002', 'bob', '无人机集群的智能协同与自适应控制', 1, datetime('now')),
    ('u003', 'charlie', '用于音频异常检测的嵌入式 AI 技术', 1, datetime('now'));


