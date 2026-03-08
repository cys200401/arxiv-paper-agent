import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field
from tqdm import tqdm

try:
    from google import genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

# 日志配置输出到 stderr
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s: %(message)s')

# --- 1. 定义大模型强制输出的数据结构 (Pydantic) ---
class EvaluatedPaper(BaseModel):
    title: str
    original_summary: str
    cn_translation: str = Field(description="摘要的高质量中文翻译")
    recommend_reason: str = Field(description="用一句话说明为什么推荐这篇论文")
    tech_tags: List[str] = Field(description="提取3个核心技术标签")

class DailyReport(BaseModel):
    date: str
    theme: str
    top_papers: List[EvaluatedPaper]

# --- 2. 本地 RAG 粗筛模块 ---
class LocalFilter:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        logging.info("正在加载本地向量模型...")
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ImportError("缺少 sentence-transformers 依赖，无法启用本地向量粗筛。") from e

        self.model = SentenceTransformer(model_name)
        
    def filter_top_k(self, papers_data: list, user_interest: str, top_k: int = 5) -> list:
        logging.info(f"开始粗筛，目标兴趣: '{user_interest}'")
        texts = [f"{p.get('title','')} {p.get('summary','')}".strip() for p in papers_data]
        
        # 计算相似度
        try:
            from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ImportError("缺少 scikit-learn 依赖，无法计算向量相似度。") from e

        interest_emb = self.model.encode([user_interest])
        paper_embs = self.model.encode(texts)
        similarities = cosine_similarity(interest_emb, paper_embs)[0]
        
        # 获取 Top K 的索引
        top_indices = similarities.argsort()[-top_k:][::-1]
        return [papers_data[i] for i in top_indices]

# 千问 DashScope OpenAI 兼容 endpoint（免费额度见阿里云百炼）
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _resolve_api_key(provider: str) -> Optional[str]:
    """解析 API Key：provider in ('qwen', 'gemini') 时返回对应 key。会 strip 掉首尾空格/换行。"""
    raw: Optional[str] = None
    if provider == "qwen":
        raw = os.getenv("DASHSCOPE_API_KEY")
    elif provider == "gemini":
        for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            v = os.getenv(k)
            if v:
                raw = v
                break
    if not raw or not raw.strip():
        return None
    return raw.strip()


def _read_json_input(path: Optional[str]) -> Any:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("没有从 stdin 接收到 JSON 数据（也未指定 --input）。")
    return json.loads(raw)


def _normalize_papers(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for k in ("papers", "data", "items", "papers_data"):
            if k in payload and isinstance(payload[k], list):
                payload = payload[k]
                break

    if not isinstance(payload, list):
        raise TypeError(f"输入 JSON 需为 list[paper] 或包含 list 的 dict，实际: {type(payload).__name__}")

    papers: List[Dict[str, Any]] = []
    for i, p in enumerate(payload):
        if not isinstance(p, dict):
            logging.warning(f"跳过非 dict 的条目: index={i}, type={type(p).__name__}")
            continue
        if "title" not in p or "summary" not in p:
            logging.warning(f"跳过缺少 title/summary 的条目: index={i}")
            continue
        papers.append(p)
    return papers


def _compact_for_prompt(papers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in papers:
        out.append(
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "authors": (p.get("authors") or [])[:8],
                "summary": p.get("summary"),
                "published_date": p.get("published_date"),
                "primary_category": p.get("primary_category"),
                "categories": p.get("categories"),
                "pdf_url": p.get("pdf_url"),
            }
        )
    return out


def _build_messages(theme: str, date_str: str, selected_papers: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    ctx = json.dumps(_compact_for_prompt(selected_papers), ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "你是一个严谨的学术智能体。你会阅读用户提供的论文 JSON 数据，基于主题挑选最有价值的论文，"
                "并严格输出符合给定 Pydantic 结构（DailyReport）的 JSON。"
                "要求：top_papers 只包含最相关的论文（不超过 5 篇），"
                "每篇论文必须包含：title、original_summary（原英文摘要，来自输入 summary）、"
                "cn_translation（高质量中文翻译）、recommend_reason（一句话推荐理由）、tech_tags（3 个核心标签）。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"报告日期：{date_str}\n"
                f"今日主题：{theme}\n\n"
                f"候选论文数据如下（JSON）：\n{ctx}"
            ),
        },
    ]


def _build_messages_single_paper(theme: str, date_str: str, paper: Dict[str, Any]) -> List[Dict[str, str]]:
    """单篇论文精读的 prompt，用于并发请求。"""
    ctx = json.dumps(_compact_for_prompt([paper]), ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "你是一个严谨的学术智能体。根据用户提供的一篇论文 JSON，"
                "输出符合 Pydantic 结构的单条结果：title、original_summary（原英文摘要）、"
                "cn_translation（高质量中文翻译）、recommend_reason（一句话推荐理由）、tech_tags（3 个核心标签）。"
            ),
        },
        {
            "role": "user",
            "content": f"报告日期：{date_str}\n今日主题：{theme}\n\n论文数据：\n{ctx}",
        },
    ]


def _evaluate_one_paper(
    instructor_client: Any,
    llm_model: str,
    theme: str,
    date_str: str,
    paper: Dict[str, Any],
) -> EvaluatedPaper:
    """对单篇论文调用 LLM 得到 EvaluatedPaper（供并发使用）。"""
    messages = _build_messages_single_paper(theme, date_str, paper)
    return instructor_client.create(
        messages=messages,
        response_model=EvaluatedPaper,
        model=llm_model,
    )


def _infer_provider(llm_model: str) -> str:
    """根据模型名推断 provider：qwen* -> qwen，否则 -> gemini。"""
    if llm_model.lower().startswith("qwen"):
        return "qwen"
    return "gemini"


def _create_instructor_client(llm_model: str) -> Any:
    try:
        import instructor  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError("缺少 instructor 依赖，无法启用结构化输出。") from e

    provider = _infer_provider(llm_model)
    api_key = _resolve_api_key(provider)
    if not api_key:
        if provider == "qwen":
            raise EnvironmentError("未检测到 DASHSCOPE_API_KEY。请先在环境变量中设置（阿里云百炼控制台可申请免费额度）。")
        raise EnvironmentError("未检测到 GEMINI_API_KEY 或 GOOGLE_API_KEY。请先在环境变量中设置。")

    if provider == "qwen":
        if OpenAI is None:
            raise ImportError("使用千问模型需要安装 openai 依赖：pip install openai")
        client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)
        return instructor.from_openai(client)
    # Gemini
    provider_model = f"google/{llm_model}" if "/" not in llm_model else llm_model
    return instructor.from_provider(provider_model, api_key=api_key)


def run_agent(
    *,
    input_path: Optional[str],
    interest: str,
    top_k: int,
    local_model: str,
    llm_model: str,
) -> DailyReport:
    payload = _read_json_input(input_path)
    papers = _normalize_papers(payload)
    logging.info(f"Agent 接收到 {len(papers)} 篇待处理论文。")

    chosen: List[Dict[str, Any]]
    if top_k <= 0:
        chosen = list(papers)
    else:
        paper_filter = LocalFilter(model_name=local_model)
        chosen = paper_filter.filter_top_k(papers, interest, top_k=min(top_k, len(papers)))

    date_str = datetime.now().strftime("%Y-%m-%d")
    instructor_client = _create_instructor_client(llm_model)
    n_papers = len(chosen)
    logging.info(f"启动大模型深度阅读与排版（并发）... model={llm_model} papers={n_papers}")

    # 并发精读每篇论文，带进度条；max_workers=3 兼顾速度与 API 限流
    max_workers = min(3, n_papers)
    evaluated: List[Optional[EvaluatedPaper]] = [None] * n_papers
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _evaluate_one_paper,
                instructor_client,
                llm_model,
                interest,
                date_str,
                paper,
            ): i
            for i, paper in enumerate(chosen)
        }
        with tqdm(total=n_papers, desc="精读论文", unit="篇", file=sys.stderr) as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    evaluated[idx] = future.result()
                except Exception as e:
                    logging.warning(f"第 {idx + 1} 篇论文精读失败: {e}")
                    p = chosen[idx]
                    evaluated[idx] = EvaluatedPaper(
                        title=p.get("title", ""),
                        original_summary=p.get("summary", ""),
                        cn_translation="(精读失败，保留原文)",
                        recommend_reason="(精读失败)",
                        tech_tags=[],
                    )
                pbar.update(1)

    top_papers = [p for p in evaluated if p is not None]
    report = DailyReport(date=date_str, theme=interest, top_papers=top_papers)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="arXiv daily agent (reads JSON from stdin, outputs report JSON to stdout)")
    parser.add_argument("--input", "-i", default=None, help="输入 JSON 文件路径（不提供则从 stdin 读取）")
    parser.add_argument(
        "--interest",
        default="AI agent orchestration, LLM application, code generation",
        help="用户兴趣/主题，用于本地粗筛与 LLM 报告主题",
    )
    parser.add_argument("--top-k", type=int, default=5, help="本地粗筛保留的论文数（<=0 表示不筛）")
    parser.add_argument("--local-model", default="all-MiniLM-L6-v2", help="SentenceTransformer 模型名")
    parser.add_argument(
        "--model",
        default="qwen-turbo",
        help="大模型名：千问 qwen-turbo（默认）/ qwen-plus，或 Gemini gemini-2.0-flash",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = run_agent(
            input_path=args.input,
            interest=args.interest,
            top_k=args.top_k,
            local_model=args.local_model,
            llm_model=args.model,
        )
    except Exception as e:
        err_msg = str(e)
        # 千问 401 = API Key 错误，给出排查提示
        if _infer_provider(args.model) == "qwen" and (
            "401" in err_msg or "Incorrect API key" in err_msg or "invalid_api_key" in err_msg
        ):
            logging.error("千问 API 认证失败（401）。请检查：")
            logging.error("  1. 环境变量 DASHSCOPE_API_KEY 是否已设置且无多余空格/换行")
            logging.error("  2. Key 是否在「阿里云百炼」控制台创建（非通用 AccessKey）：https://dashscope.console.aliyun.com/")
            logging.error("  3. 是否已开通百炼模型服务并复制了完整的 API Key")
        else:
            logging.error(err_msg)
        return 1

    sys.stdout.write(report.model_dump_json(indent=2, by_alias=True))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())