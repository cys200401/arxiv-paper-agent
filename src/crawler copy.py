import json
import time
import os
import re
import requests
import random  # 新增：用于生成随机延迟
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List
from tqdm import tqdm  
from pydantic import BaseModel, Field, ConfigDict  # 新增：引入 ConfigDict
from tenacity import retry, stop_after_attempt, wait_exponential
import feedparser

# ==========================================
# 1. 数据模型
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
# 2. 爬虫引擎
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
                    print(f"\n❌ 获取列表失败: {e}")
                    time.sleep(5)
        return papers[:target_count]

    def download_pdfs(self, papers: List[PaperModel], save_dir: str):
        """批量下载 PDF：并发 + 连接复用 + 原子落盘，避免半残文件"""
        os.makedirs(save_dir, exist_ok=True)
        print(f"\n📥 开始下载 {len(papers)} 篇论文的 PDF 到 {save_dir}/ ...")

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

        print(
            f"\n📌 PDF 下载统计: ok={results['ok']} skip={results['skip']} blocked={results['blocked']} "
            f"timeout={results['timeout']} failed={results['failed']}"
        )
# ==========================================
# 3. 执行调度
# ==========================================
def main():
    CATEGORIES = {"cs.AI": 40, "cs.CV": 40, "cs.LG": 40, "cs.CL": 40, "cs.RO": 40}
    fetcher = ArxivFetcher(delay=3.0) 
    all_papers: List[PaperModel] = []
    
    print("🎯 第一阶段：获取 200 篇论文的元数据信息...")
    for cat, count in CATEGORIES.items():
        all_papers.extend(fetcher.fetch_category(cat, count))
    
    output_json = "papers_dataset.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in all_papers], f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 元数据已保存至 {output_json}")

    # ==========================================
    # 重点：触发批量 PDF 下载
    # ==========================================
    pdf_dir = "papers_pdf"
    fetcher.download_pdfs(all_papers, save_dir=pdf_dir)

    print("\n" + "="*50)
    print("🎉 完美收工！")
    print(f"📊 成功入库元数据: {len(all_papers)} 篇")
    print(f"📁 PDF 实体文件存放路径: ./{pdf_dir}/")
    print("="*50)

if __name__ == "__main__":
    main()