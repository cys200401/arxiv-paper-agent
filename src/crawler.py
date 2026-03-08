import argparse
import json
import time
import os
import re
import requests
import random  # 新增：用于生成随机延迟
import threading
import sys       # 确保导入 sys
import logging   # 【新增】用于区分 stdout/stderr 输出流
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List
from tqdm import tqdm  
from pydantic import BaseModel, Field, ConfigDict  # 新增：引入 ConfigDict
from tenacity import retry, stop_after_attempt, wait_exponential
import feedparser

# ==========================================
# 1. 数据模型（保持不变）
# ==========================================
class PaperModel(BaseModel):
    id: str = Field(..., description="Arxiv ID")
    title: str = Field(..., description="标题")
    authors: List[str] = Field(default_factory=list)
    summary: str = Field(..., description="摘要")
    published_date: str = Field(..., description="发布时间")
    pdf_url: str = Field(..., description="PDF链接")
    primary_category: str = Field(..., description="主类别")
    categories: List[str] = Field(default_factory=list, description="所有类别")
    
    # 修复：使用 Pydantic V2 的标准配置方式，消除弃用警告
    model_config = ConfigDict(extra="allow")

# ==========================================
# 2. 爬虫引擎（保持不变）
# ==========================================
class ArxivFetcher:
    def __init__(
        self,
        delay: float = 3.0,
        *,
        pdf_delay: float = 0.2,
        pdf_workers: int = 4,
    ):
        self.base_url = "http://export.arxiv.org/api/query"
        # arXiv API 文档建议：连续调用 query 接口时加入约 3 秒延迟
        self.delay = delay

        # PDF 下载通常更耗时；这里用“低延迟 + 小并发”代替逐篇长时间 sleep
        self.pdf_delay = max(0.0, float(pdf_delay))
        self.pdf_workers = max(1, int(pdf_workers))

        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        self.session = self._create_session()
        self._thread_local = threading.local()

    def _create_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": self._user_agent})
        # 适度放大连接池，配合线程池复用连接
        adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def _get_pdf_session(self) -> requests.Session:
        s = getattr(self._thread_local, "session", None)
        if s is None:
            s = self._create_session()
            self._thread_local.session = s
        return s
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_batch(self, query: str, start: int, batch_size: int) -> List[PaperModel]:
        params = {
            "search_query": query, "start": start,
            "max_results": batch_size, "sortBy": "submittedDate", "sortOrder": "descending"
        }
        response = self.session.get(self.base_url, params=params, timeout=15)
        response.raise_for_status()
        return self._parse_xml(response.text)

    def _clean_text(self, text: str) -> str:
        if not text: return ""
        text = text.replace('\n', ' ')
        return re.sub(r'\s+', ' ', text).strip()

    def _parse_xml(self, xml_data: str) -> List[PaperModel]:
        feed = feedparser.parse(xml_data)
        papers = []
        for entry in feed.entries:
            pdf_url = next(
                (link.href for link in entry.links if link.get('title') == 'pdf'), 
                entry.link
            )
            if not pdf_url.endswith('.pdf'):
                pdf_url += '.pdf'
            
            categories = [tag.term for tag in entry.tags] if hasattr(entry, 'tags') else []
            primary_cat = entry.arxiv_primary_category.get('term') if hasattr(entry, 'arxiv_primary_category') and 'term' in entry.arxiv_primary_category else (categories[0] if categories else "unknown")
            
            paper = PaperModel(
                id=entry.id.split('/abs/')[-1].split('v')[0], 
                title=self._clean_text(entry.title),
                authors=[author.name for author in entry.authors] if hasattr(entry, 'authors') else [],
                summary=self._clean_text(entry.summary),
                published_date=entry.published,
                pdf_url=pdf_url,
                primary_category=primary_cat,
                categories=categories
            )
            papers.append(paper)
        return papers

    def fetch_category(self, category: str, target_count: int, batch_size: int = 50) -> List[PaperModel]:
        query = f"cat:{category}"
        papers, start = [], 0
        
        # tqdm 默认输出到 stderr，符合管道通信要求
        with tqdm(total=target_count, desc=f"获取 {category} 列表", leave=False) as pbar:
            while len(papers) < target_count:
                current_batch = min(batch_size, target_count - len(papers))
                try:
                    batch = self.fetch_batch(query, start, current_batch)
                    if not batch: break
                    papers.extend(batch)
                    start += len(batch)
                    pbar.update(len(batch))
                    time.sleep(self.delay)
                except Exception as e:
                    # 使用 logging 输出到 stderr，避免污染 stdout
                    logging.error(f"获取列表失败: {e}")
                    time.sleep(5)
        return papers[:target_count]

    def download_pdfs(self, papers: List[PaperModel], save_dir: str):
        """批量下载 PDF：并发 + 连接复用 + 原子落盘，避免半残文件"""
        os.makedirs(save_dir, exist_ok=True)
        logging.info(f"开始下载 {len(papers)} 篇论文的 PDF 到 {save_dir}/ ...")

        def _download_one(paper: PaperModel) -> str:
            safe_id = paper.id.replace("/", "_")
            filepath = os.path.join(save_dir, f"{safe_id}.pdf")
            part_filepath = filepath + ".part"

            if os.path.exists(filepath):
                return "skip"

            session = self._get_pdf_session()
            max_retries = 3

            for attempt in range(1, max_retries + 1):
                try:
                    # 轻量抖动，避免所有线程同时打满
                    if self.pdf_delay > 0:
                        time.sleep(self.pdf_delay + random.uniform(0, self.pdf_delay))

                    response = session.get(paper.pdf_url, stream=True, timeout=(15, 120))

                    # 常见：触发限流/维护时给 429/503；交给重试退避
                    if response.status_code in (429, 503):
                        raise requests.HTTPError(
                            f"HTTP {response.status_code}",
                            response=response,
                        )

                    response.raise_for_status()

                    content_type = (response.headers.get("Content-Type", "") or "").lower()

                    with open(part_filepath, "wb") as f:
                        first_chunk = None
                        for chunk in response.iter_content(chunk_size=1024 * 64):
                            if not chunk:
                                continue
                            if first_chunk is None:
                                first_chunk = chunk
                            f.write(chunk)

                    # 双重校验：header 或文件头魔数
                    is_pdf = ("pdf" in content_type) or (
                        first_chunk is not None and first_chunk.lstrip().startswith(b"%PDF-")
                    )
                    if not is_pdf:
                        if os.path.exists(part_filepath):
                            os.remove(part_filepath)
                        return "blocked"

                    os.rename(part_filepath, filepath)
                    return "ok"

                except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
                    # 断连/IncompleteRead
                    if attempt < max_retries:
                        time.sleep(min(10, 2 ** attempt))
                        continue
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return f"conn_error:{type(e).__name__}"

                except requests.exceptions.Timeout:
                    if attempt < max_retries:
                        time.sleep(min(10, 2 ** attempt))
                        continue
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return "timeout"

                except requests.HTTPError as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    # 对 429/503 做更保守的退避
                    if status in (429, 503) and attempt < max_retries:
                        time.sleep(min(30, 5 * attempt))
                        continue
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return f"http_error:{status}"

                except Exception as e:
                    if os.path.exists(part_filepath):
                        os.remove(part_filepath)
                    return f"error:{type(e).__name__}"

            if os.path.exists(part_filepath):
                os.remove(part_filepath)
            return "failed"

        results = {"ok": 0, "skip": 0, "blocked": 0, "timeout": 0, "failed": 0}
        other_errors = 0

        with ThreadPoolExecutor(max_workers=self.pdf_workers) as ex:
            futures = [ex.submit(_download_one, p) for p in papers]
            for fut in tqdm(as_completed(futures), total=len(futures), desc="PDF 下载进度"):
                r = fut.result()
                if r in results:
                    results[r] += 1
                elif r.startswith("conn_error:") or r.startswith("http_error:") or r.startswith("error:"):
                    other_errors += 1
                else:
                    results["failed"] += 1

        if other_errors:
            results["failed"] += other_errors

        logging.info(
            f"PDF 下载统计: ok={results['ok']} skip={results['skip']} blocked={results['blocked']} "
            f"timeout={results['timeout']} failed={results['failed']}"
        )

# ==========================================
# 3. 执行调度（【核心改造区域】）
# ==========================================
def _fetch_by_query(fetcher: ArxivFetcher, query: str, target_count: int, batch_size: int = 50) -> List[PaperModel]:
    """按任意 search_query 拉取论文，直到达到 target_count（与 fetch_category 逻辑一致）。"""
    papers, start = [], 0
    with tqdm(total=target_count, desc=f"获取 query 列表", leave=False) as pbar:
        while len(papers) < target_count:
            current_batch = min(batch_size, target_count - len(papers))
            try:
                batch = fetcher.fetch_batch(query, start, current_batch)
                if not batch:
                    break
                papers.extend(batch)
                start += len(batch)
                pbar.update(len(batch))
                time.sleep(fetcher.delay)
            except Exception as e:
                logging.error(f"获取列表失败: {e}")
                time.sleep(5)
    return papers[:target_count]


def main():
    """
    【管道通信模式】
    运行方式: python crawler.py [--query <topic>] | python agent.py
    原理：所有日志/诊断信息 -> stderr；仅 JSON 数据 -> stdout
    """
    parser = argparse.ArgumentParser(description="arXiv crawler: output papers JSON to stdout for pipeline.")
    parser.add_argument(
        "--query",
        default=None,
        help="arXiv search_query（如 cat:cs.AI 或 all:machine learning）；不传则使用多类别默认抓取",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        metavar="N",
        help="使用 --query 时最多拉取的论文数（默认 100）",
    )
    args = parser.parse_args()

    # 【关键改动 1】强制将日志输出到 stderr，避免污染传给 Agent 的数据流
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    fetcher = ArxivFetcher(delay=3.0)
    all_papers: List[PaperModel] = []

    if args.query is not None:
        logging.info("🎯 按 query 获取论文元数据（标题、摘要、作者等）...")
        logging.info(f"query=%s, max_results=%s", args.query, args.max_results)
        all_papers = _fetch_by_query(fetcher, args.query, args.max_results)
    else:
        CATEGORIES = {"cs.AI": 40, "cs.CV": 40, "cs.LG": 40, "cs.CL": 40, "cs.RO": 40}
        logging.info("🎯 第一阶段：获取 200 篇论文的元数据（标题、摘要、作者等，非 PDF 全文）...")
        for cat, count in CATEGORIES.items():
            logging.info(f"正在获取类别 {cat} 的 {count} 篇论文...")
            papers = fetcher.fetch_category(cat, count)
            all_papers.extend(papers)
            logging.info(f"类别 {cat} 获取完成，当前总数: {len(all_papers)}")

    # 【关键改动 2】将论文列表转换为字典列表，准备序列化
    papers_data = [p.model_dump() for p in all_papers]

    # 【关键改动 3】不写文件，直接将 JSON 字符串严格输出到标准输出 (stdout)
    json_output = json.dumps(papers_data, ensure_ascii=False, indent=2)
    sys.stdout.write(json_output)
    sys.stdout.flush()

    logging.info(f"✅ 成功获取 {len(all_papers)} 篇论文元数据，已通过管道传给 Agent 做粗筛与精读")


if __name__ == "__main__":
    main()