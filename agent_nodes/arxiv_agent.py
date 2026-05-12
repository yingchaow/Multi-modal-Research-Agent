import os
import random
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET 
import asyncio  
import httpx   

from state import ResearchState
from config import paper_filter_model
from skills.paper_screening import paper_screening_skill

from memory.paper_seen import is_paper_seen, mark_paper_as_seen, get_query_max_offset, update_query_max_offset


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_REQUEST_INTERVAL = float(os.getenv("ARXIV_REQUEST_INTERVAL", "8"))
ARXIV_MAX_RETRIES = int(os.getenv("ARXIV_MAX_RETRIES", "6"))
ARXIV_MAX_PAGES_PER_RUN = int(os.getenv("ARXIV_MAX_PAGES_PER_RUN", "4"))
ARXIV_BATCH_SIZE = int(os.getenv("ARXIV_BATCH_SIZE", "20"))
ARXIV_USER_AGENT = os.getenv(
    "ARXIV_USER_AGENT",
    "cross-model-retrieval-agent/1.0 (research use; contact: local-user)",
)

_arxiv_request_lock = asyncio.Lock()
_last_arxiv_request_at = 0.0


async def wait_for_arxiv_slot() -> None:
    """Throttle Arxiv API requests across concurrent workflow runs."""
    global _last_arxiv_request_at

    async with _arxiv_request_lock:
        elapsed = time.monotonic() - _last_arxiv_request_at
        wait_time = ARXIV_REQUEST_INTERVAL - elapsed
        if wait_time > 0:
            jitter = random.uniform(0.2, 1.2)
            sleep_for = wait_time + jitter
            print(f"[Arxiv 节流] 距离上次请求过近，等待 {sleep_for:.1f} 秒...")
            await asyncio.sleep(sleep_for)

        _last_arxiv_request_at = time.monotonic()


def retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None

    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        return max(float(retry_after), ARXIV_REQUEST_INTERVAL)
    except ValueError:
        return None


def arxiv_backoff_seconds(attempt: int, response: httpx.Response | None = None) -> float:
    server_wait = retry_after_seconds(response)
    if server_wait is not None:
        return server_wait + random.uniform(1.0, 3.0)

    base = min(ARXIV_REQUEST_INTERVAL * (2 ** attempt), 240)
    return base + random.uniform(1.0, 5.0)


async def fetch_arxiv_xml(client: httpx.AsyncClient, url: str) -> str:
    headers = {
        "User-Agent": ARXIV_USER_AGENT,
        "Accept": "application/atom+xml, application/xml;q=0.9, text/xml;q=0.8",
    }

    last_error = None
    for attempt in range(ARXIV_MAX_RETRIES):
        await wait_for_arxiv_slot()

        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            last_error = e
            status_code = e.response.status_code
            if status_code == 429:
                wait_time = arxiv_backoff_seconds(attempt, e.response)
                print(f"  [Arxiv 限流] 触发 429，第 {attempt + 1}/{ARXIV_MAX_RETRIES} 次退避 {wait_time:.1f} 秒...")
                await asyncio.sleep(wait_time)
                continue

            if 500 <= status_code < 600:
                wait_time = arxiv_backoff_seconds(attempt, e.response)
                print(f"  [Arxiv 服务端错误] {status_code}，退避 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)
                continue

            raise
        except httpx.RequestError as e:
            last_error = e
            wait_time = arxiv_backoff_seconds(attempt)
            print(f"  [Arxiv 网络波动] {e}，退避 {wait_time:.1f} 秒后重试...")
            await asyncio.sleep(wait_time)

    raise RuntimeError(f"Arxiv API 多次重试后仍失败：{last_error}")


def normalize_arxiv_keyword(keyword: str) -> str:
    keyword = re.sub(r"\s+", " ", str(keyword or "")).strip()
    return keyword.strip("\"'`，,;；")


def build_arxiv_search_query(search_query: str, keywords: list[str] | None = None) -> str:
    clean_keywords = [
        normalize_arxiv_keyword(keyword)
        for keyword in (keywords or [])
        if normalize_arxiv_keyword(keyword)
    ]

    if clean_keywords:
        clauses = []
        for keyword in clean_keywords[:5]:
            escaped = keyword.replace('"', "")
            if " " in escaped:
                clauses.append(f'all:"{escaped}"')
            else:
                clauses.append(f"all:{escaped}")
        return " OR ".join(clauses)

    search_query = str(search_query or "").strip()
    if " OR " in search_query or search_query.startswith("all:"):
        return search_query
    if " " in search_query:
        return f'all:"{search_query}"'
    return f"all:{search_query}"


def get_arxiv_pdf_url(arxiv_url: str) -> str:
    """将网页版链接转换为直达的 PDF 链接"""
    if "abs" in arxiv_url:
        return arxiv_url.replace("/abs/", "/pdf/") + ".pdf"
    return arxiv_url


def get_atom_text(entry, path: str, ns: dict, default: str = "") -> str:
    node = entry.find(path, ns)
    return node.text.replace('\n', ' ').strip() if node is not None and node.text else default


def format_paper_material(
    title: str,
    authors: list[str],
    published: str,
    categories: list[str],
    abstract: str,
    paper_url: str,
    pdf_url: str,
) -> str:
    return (
        "【论文元数据】\n"
        f"标题: {title}\n"
        f"作者: {', '.join(authors) if authors else 'Arxiv 未提供'}\n"
        f"发布日期: {published or 'Arxiv 未提供'}\n"
        f"主题分类: {', '.join(categories) if categories else 'Arxiv 未提供'}\n"
        f"摘要: {abstract}\n"
        f"Arxiv 页面: {paper_url}\n"
        f"PDF 链接: {pdf_url}\n"
    )


async def arxiv_agent_node(state: ResearchState):
    # 优先使用英文关键词，兜底使用原始 topic
    search_query = state.get('english_topic', state.get('topic', ''))
    search_keywords = state.get('search_keywords', [])
    user_topic = state.get('topic', search_query)
    historical_max_offset = get_query_max_offset(search_query)
    
    current_batch_size = ARXIV_BATCH_SIZE  # Arxiv 建议单次请求不要太大，20-50 比较合适
    current_offset = historical_max_offset
    pages_scanned = 0
    
    # Arxiv 对自动请求比较敏感，这里使用全局节流和退避，避免连续翻页触发限流。
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while True:
            if pages_scanned >= ARXIV_MAX_PAGES_PER_RUN:
                reason = (
                    f"本轮已扫描 {pages_scanned} 页 Arxiv 结果，未找到通过初筛的新论文。"
                    "为避免触发 Arxiv 限流，已暂停本轮检索；稍后重试会从当前进度继续。"
                )
                print(f"[Arxiv 节点] {reason}")
                return {
                    "review_feedback": "[SEARCH_EXHAUSTED]",
                    "node_error": reason,
                    "next_node": "FINISH",
                }

            # Arxiv API 查询参数构建
            params = {
                "search_query": build_arxiv_search_query(search_query, search_keywords),  # 搜索全部字段
                "start": current_offset,
                "max_results": current_batch_size,
                "sortBy": "submittedDate",             # 按最新发布时间排序
                "sortOrder": "descending"
            }
            query_string = urllib.parse.urlencode(params)
            url = f"{ARXIV_API_URL}?{query_string}"
            
            try:
                print(f"正在请求 Arxiv API (start={current_offset}, 抓取数量={current_batch_size})...")
                xml_data = await fetch_arxiv_xml(client, url)
                pages_scanned += 1
                
                # 🌟 解析 XML
                root = ET.fromstring(xml_data)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}  # Arxiv 的 XML 命名空间
                
                entries = root.findall('atom:entry', ns)
                
                if not entries:
                    print("[Arxiv 节点] 警告：该关键词下的最新论文已全部耗尽！")
                    reason = "当前关键词下没有找到新的可用论文，或已读论文记录已经覆盖了本批结果。"
                    return {
                        "review_feedback": "[SEARCH_EXHAUSTED]",
                        "node_error": reason,
                        "next_node": "FINISH"
                    }
                    
                scanned_in_batch = 0
                
                for entry in entries:
                    scanned_in_batch += 1
                    
                    # 提取基础信息
                    paper_url = get_atom_text(entry, 'atom:id', ns)
                    paper_id = paper_url.split('/')[-1]  # 取出末尾的 ID (例如 2404.16670v1)
                    title = get_atom_text(entry, 'atom:title', ns, "未知标题")
                    abstract = get_atom_text(entry, 'atom:summary', ns)
                    published = get_atom_text(entry, 'atom:published', ns)
                    authors = [
                        get_atom_text(author, 'atom:name', ns)
                        for author in entry.findall('atom:author', ns)
                    ]
                    authors = [author for author in authors if author]
                    categories = [
                        category.attrib.get("term", "").strip()
                        for category in entry.findall('atom:category', ns)
                        if category.attrib.get("term")
                    ]
                    
                    # 直接转换为 PDF 下载链接
                    pdf_url = get_arxiv_pdf_url(paper_url)

                    # 如果这篇论文已经看过了，跳过
                    if is_paper_seen(paper_id):
                        continue
                    
                    print(f"   来源: Arxiv 预印本")
                    print(f"   标题: 《{title}》")
                    print(f"   直链: {pdf_url}")

                    should_read, filter_reason, filter_warning = await paper_screening_skill.arun(
                        user_topic=user_topic,
                        search_query=search_query,
                        title=title,
                        abstract=abstract,
                        categories=categories,
                        model=paper_filter_model,
                    )

                    absolute_depth = current_offset + scanned_in_batch
                    update_query_max_offset(search_query, absolute_depth)

                    if not should_read:
                        print(f"   [AI 初筛] 跳过：{filter_reason}")
                        mark_paper_as_seen(paper_id, title, status="FILTERED_OUT")
                        continue

                    print(f"   [AI 初筛] 通过：{filter_reason}")
                    
                    # 记录到记忆库
                    mark_paper_as_seen(paper_id, title, status="SELECTED")
                    
                    paper_material = format_paper_material(
                        title=title,
                        authors=authors,
                        published=published,
                        categories=categories,
                        abstract=abstract,
                        paper_url=paper_url,
                        pdf_url=pdf_url,
                    )
                    paper_material += f"AI 初筛结论: {filter_reason}\n"
                    current_paper = {
                        "title": f"[Arxiv] {title}",
                        "url": pdf_url,
                        "page_url": paper_url,
                        "authors": authors,
                        "published": published,
                        "categories": categories,
                        "abstract": abstract,
                        "screening_decision": filter_reason,
                    }
                    
                    # 找到一篇全新论文后，立刻返回并流转到下一个节点
                    return {
                        "current_source_paper": current_paper,
                        "arxiv_papers": [paper_material],  # 传给多模态/架构师节点的结构化论文材料
                        "review_feedback": "",       
                        "review_retry_count": 0,      
                        "is_exit": None,
                        "next_node": "multimodal_agent", # 🌟 跳转到你处理 PDF/图片的节点
                        "node_error": "",
                        "node_warning": filter_warning,
                    }
                
                # 如果这批数据都已处理或被初筛跳过，继续翻页
                current_offset += len(entries)
                update_query_max_offset(search_query, current_offset)
                # 为避免频繁请求被封，翻页前强制等待，比官方最低间隔更保守。
                page_wait = ARXIV_REQUEST_INTERVAL + random.uniform(1.0, 3.0)
                await asyncio.sleep(page_wait)
                print(f"本批次 {len(entries)} 篇均已处理或被初筛跳过，推至 start={current_offset} ...")
                
            except Exception as e:
                print(f"[Arxiv 节点] 致命错误: {e}")
                return {
                    "review_feedback": "[SEARCH_FAILED]",
                    "node_error": f"Arxiv 检索失败：{e}",
                    "next_node": "FINISH"
                }
