# Railway 部署说明

## 当前数据库方案

项目现在只使用 SQLite，不再连接 Turso/libSQL。应用启动时会自动初始化 `users` 和 `daily_reports` 表，并默认把数据库文件放在用户下载目录下的 `~/Downloads/arxiv_data/papers.db`。在你的机器上，这会解析为 `/Users/chenyushi/Downloads/arxiv_data/papers.db`。

## Railway Variables

在 [Railway](https://railway.app) 的 **Variables** 中，当前真正需要的只有以下变量：

| 变量名 | 说明 | 示例/取值 |
|--------|------|-----------|
| `RAILPACK_PYTHON_VERSION` | 构建用 Python 版本 | `3.12` |
| `API_SECRET_KEY` | 接口鉴权密钥 | 自定义一个强随机字符串 |
| `SQLITE_DATABASE_PATH` | 可选，自定义 SQLite 文件路径 | `/Users/chenyushi/Downloads/arxiv_data/papers.db` |

### 关于你现有的 Turso 变量

如果你之前已经在 Railway 配置了：

```text
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
```

现在**不用删除，也不用来回改网页配置**。应用会自动忽略这两个旧变量中的远程 libSQL 配置，直接回退到 SQLite。也就是说，保留它们不会阻止服务启动。

只有一种例外：如果你把 `TURSO_DATABASE_URL` 设成了 `file:...`，应用会把它当作 SQLite 文件路径继续使用。

## 推荐配置

- 最省事的做法：只保留 `API_SECRET_KEY`，让应用默认使用 `~/Downloads/arxiv_data/papers.db`；在你的机器上就是 `/Users/chenyushi/Downloads/arxiv_data/papers.db`。
- 如果你后面在 Railway 挂了持久卷，可以再额外设置 `SQLITE_DATABASE_PATH` 指向卷内路径；这一步是可选的，不影响当前切换到 SQLite。

## 鉴权说明

`/api/v1/ingest` 和 `/api/v1/reports` 仍然要求：

```text
Authorization: Bearer <API_SECRET_KEY>
```

保存变量后重新部署即可，无需再配置 Turso。
