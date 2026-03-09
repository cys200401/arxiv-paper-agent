# Pipeline 三级验证指南

按「本地单元测试 → 管道集成测试 → 云端端到端测试」逐步验证流水线是否有效。

---

## 一、本地单元测试

验证各模块行为与 API 契约，不依赖网络或外部服务（除 API 测试可能用本地 DB）。

### 运行

```bash
# 安装依赖（含 pytest）
pip install -r requirements.txt -r requirements-dev.txt

# 从仓库根目录执行
PYTHONPATH=src python -m pytest tests/test_crawler.py tests/test_agent.py tests/test_api.py -v
```

### 覆盖内容

| 模块 | 测试文件 | 要点 |
|------|----------|------|
| Crawler | `tests/test_crawler.py` | `--query` / `--max-results` 解析，`_fetch_by_query` 在 mock 下行为，main 输出合法 JSON。也可用模块入口：`python -m src.cli.crawler --query "…" --target 5 --output papers.json` |
| Agent | `tests/test_agent.py` | `_normalize_papers`（list/dict 输入）、`DailyReport`/`EvaluatedPaper` 解析与 JSON 往返 |
| API | `tests/test_api.py` | `IngestBody` 校验、POST `/api/v1/ingest` 需 Bearer、合法 payload 返回 200/503 |

---

## 二、管道集成测试

在本地真实执行 `crawler | agent`，用较小数据量（少量论文、少量 top-k），校验 stdout 为合法 `DailyReport` JSON。

### 运行

**方式 A：pytest（需配置 LLM Key）**

```bash
# 千问（阿里云百炼）
export DASHSCOPE_API_KEY="your-key"
# 或 Gemini
export GEMINI_API_KEY="your-key"

PYTHONPATH=src python -m pytest tests/test_pipeline_integration.py -v
```

未设置任一 Key 时该测试会自动 **skip**。若同时设置，优先使用千问（`qwen-turbo`）。

**方式 B：脚本**

```bash
export DASHSCOPE_API_KEY="your-key"   # 千问，与日常使用一致
# 或 export GEMINI_API_KEY="your-key"
./scripts/run_integration_test.sh
```

脚本会执行 `crawler --query cat:cs.AI --max-results 5 | agent --interest cs.AI --top-k 2`（模型按 Key 自动选千问或 Gemini），并用 Python 校验输出为 `DailyReport`。

### 通过标准

- 管道退出码为 0。
- 标准输出可被解析为 JSON，且符合 `DailyReport`（含 `date`、`theme`、`top_papers`，每篇含 `title`、`original_summary`、`cn_translation`、`tech_tags` 等）。

---

## 三、云端端到端测试

在 **GitHub Actions** 里跑完整流水线（crawler → agent → POST 到 Railway），再在 **Railway** 上确认日报是否写入成功。

**前提**：代码已推到 GitHub 仓库，且 Railway 上 API 已部署并能访问（见 RAILWAY.md）。

---

### 步骤 1：在 GitHub 配置 Secrets

1. 打开你的 **GitHub 仓库** → 顶部 **Settings**。
2. 左侧 **Secrets and variables** → **Actions**。
3. 点 **New repository secret**，按下面逐个添加（名称必须一致）：

| Name | 说明 | 示例值 |
|------|------|--------|
| `GEMINI_API_KEY` | Agent 用的 Gemini API 密钥（云端 workflow 当前用 Gemini）。须从 [Google AI Studio](https://aistudio.google.com/apikey) 获取或于 Google Cloud 启用 Generative Language API；无效或为空会报 `API key not valid`。 | `AIza...` |
| `API_HOST` | Railway 应用根地址，**要带 `https://`** | `https://your-app.up.railway.app` |
| `API_SECRET_KEY` | 与 Railway 环境变量里的 `API_SECRET_KEY` **完全一致** | 你设的一串密钥 |

若本地用千问、云端也想用千问，需在 workflow 里增加 `DASHSCOPE_API_KEY` 并改为 `--model qwen-turbo`（当前默认是 Gemini）。

---

### 步骤 2：在 GitHub 手动触发一次 workflow

1. 仓库顶部点 **Actions**。
2. 左侧 workflow 列表里选 **E2E Smoke**（推荐先跑这个，只跑 1 个 job，更快）。
3. 右侧点 **Run workflow** 下拉 → 选分支（如 `main`）→ 再点绿色 **Run workflow**。
4. 等列表里出现这一次运行，点进去 → 再点 **smoke** job，看日志。

**通过标准**：  
- 所有 step（Checkout、Set up Python、Install dependencies、Run crawler and agent、Ingest to Railway API）都打勾。  
- 若 **Ingest to Railway API** 报错（如 `curl: (22) The requested URL returned error: 401`），说明 `API_SECRET_KEY` 或 `API_HOST` 不对，回步骤 1 检查。

跑通 **E2E Smoke** 后，可再选 **Daily Pipeline**，同样 **Run workflow**，会跑 3 个 matrix job（user_1、user_2、user_3）。

---

### 步骤 3：在 Railway 上验证数据是否写入

用你本机的终端调 Railway 的接口，确认当天有日报记录。

1. 准备三个变量（或直接替换下面的占位符）：
   - `API_HOST`：同步骤 1，如 `https://your-app.up.railway.app`
   - `API_SECRET_KEY`：同步骤 1

2. 执行（把 `YOUR_API_HOST` 和 `YOUR_API_SECRET_KEY` 换成真实值）：

```bash
curl -s -H "Authorization: Bearer YOUR_API_SECRET_KEY" \
  "YOUR_API_HOST/api/v1/reports?user_id=user_1&limit=5"
```

3. 看返回的 JSON：
   - `reports` 数组里应至少有一条记录。
   - 其中一条的 `report_date` 应为**今天**（UTC 日期，如 `2025-03-08`）。
   - `theme` 应对应 workflow 里该 job 的 topic（E2E Smoke 里是 `cat:cs.AI`）。
   - `content_json` 应为 DailyReport 结构（含 `date`、`theme`、`top_papers` 等）。

**示例**（片段）：

```json
{
  "user_id": "user_1",
  "reports": [
    {
      "id": "...",
      "user_id": "user_1",
      "report_date": "2025-03-08",
      "theme": "cat:cs.AI",
      "content_json": { "date": "2025-03-08", "theme": "cat:cs.AI", "top_papers": [...] },
      "created_at": "..."
    }
  ],
  "count": 1
}
```

若 `reports` 为空或没有当天日期，说明 ingest 未成功，回步骤 2 看 Actions 里 **Ingest to Railway API** 的报错。

---

### 可选：E2E Smoke 与 Daily Pipeline 区别

| 项目 | E2E Smoke | Daily Pipeline |
|------|-----------|----------------|
| 文件 | `.github/workflows/e2e_smoke.yml` | `.github/workflows/daily_pipeline.yml` |
| 触发 | 仅手动 **Run workflow** | 每日 00:00 UTC 自动 + 手动 |
| Matrix | 1 个 job（user_1 + cat:cs.AI） | 3 个 job（user_1/user_2/user_3 + 不同 topic） |
| 用途 | 先验证「管道 + 写入」是否通 | 正式每日三用户日报 |

---

## 小结

| 级别 | 命令/操作 | 通过条件 |
|------|-----------|----------|
| 单元测试 | `PYTHONPATH=src pytest tests/test_crawler.py tests/test_agent.py tests/test_api.py -v` | 全部通过 |
| 集成测试 | `pytest tests/test_pipeline_integration.py -v` 或 `./scripts/run_integration_test.sh` | 输出为合法 DailyReport |
| 端到端 | Actions 手动 Run workflow → 查 Railway `/api/v1/reports` | Job 成功且 DB 中有对应日报 |
