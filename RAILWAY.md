# Railway 部署说明

## 环境变量配置

登录 [Railway](https://railway.app)，连接你的 GitHub 仓库。在项目的 **Variables（环境变量）** 中，严格填入以下三个值：

| 变量名 | 说明 | 示例/取值 |
|--------|------|-----------|
| `TURSO_DATABASE_URL` | Turso 数据库地址 | `libsql://你的数据库地址.turso.io` |
| `TURSO_AUTH_TOKEN` | Turso 认证 Token | 在 Turso 控制台生成的 Token |
| `API_SECRET_KEY` | 接口鉴权密钥 | 自定义一个强密码（建议随机长字符串） |

### 填写示例（仅作格式参考，勿直接使用）

```
TURSO_DATABASE_URL = libsql://你的数据库地址.turso.io
TURSO_AUTH_TOKEN = 你刚刚生成的 Token
API_SECRET_KEY = 自定义一个强密码
```

- **TURSO_DATABASE_URL**：在 [Turso](https://turso.tech) 创建数据库后，在控制台复制「Database URL」。
- **TURSO_AUTH_TOKEN**：同一项目中生成 Token（如 `turso db tokens create <数据库名>` 或控制台生成）。
- **API_SECRET_KEY**：自行设定强密码，用于保护 `/api/v1/ingest`、`/api/v1/reports` 等接口；调用时在请求头中携带 `X-API-Key: <API_SECRET_KEY>`。

保存后重新部署，应用会使用上述环境变量连接 Turso 并启用 API 鉴权。
