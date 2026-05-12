import os
import uuid
from datetime import datetime
from typing import Any

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import QDRANT_API_KEY, QDRANT_CLOUDE_URL, embeddings_model
from state import ResearchState


COLLECTION_NAME = "paper_knowledge"
VECTOR_SIZE = 1536
MAX_REPORT_CHARS = 6000
MAX_CONTEXT_CHARS = 2400
MAX_EMBEDDING_CHARS = 1800

_knowledge_store: QdrantVectorStore | None = None


def _clear_proxy_env() -> None:
    os.environ["NO_PROXY"] = "*"
    for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        os.environ.pop(key, None)


def _qdrant_available() -> bool:
    if not QDRANT_CLOUDE_URL:
        return False
    if QDRANT_CLOUDE_URL.startswith("https") and not QDRANT_API_KEY:
        return False
    return True


def _qdrant_api_key() -> str | None:
    if QDRANT_CLOUDE_URL and QDRANT_CLOUDE_URL.startswith("https"):
        return QDRANT_API_KEY
    return None


def _shorten(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[内容已截断]"


def _paper_id_from_metadata(paper: dict[str, Any]) -> str:
    raw_id = (
        paper.get("paper_id")
        or paper.get("page_url")
        or paper.get("url")
        or paper.get("title")
        or str(uuid.uuid4())
    )
    return str(raw_id).split("/")[-1]


def _split_for_embedding(text: str, max_chars: int = MAX_EMBEDDING_CHARS) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []

    chunks = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        if end < len(text):
            newline_break = text.rfind("\n", cursor, end)
            sentence_break = max(
                text.rfind("。", cursor, end),
                text.rfind(".", cursor, end),
            )
            split_at = max(newline_break, sentence_break)
            if split_at > cursor + max_chars * 0.5:
                end = split_at + 1

        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(chunk)
        cursor = end

    return chunks


def _ensure_collection_exists() -> None:
    if not _qdrant_available():
        raise RuntimeError("Qdrant 配置缺失：请检查 QDRANT_CLOUDE_URL；云端 https 地址还需要 QDRANT_API_KEY。")

    _clear_proxy_env()
    client = QdrantClient(
        url=QDRANT_CLOUDE_URL,
        api_key=_qdrant_api_key(),
        timeout=10,
        check_compatibility=False,
    )
    try:
        if not client.collection_exists(COLLECTION_NAME):
            print(f"[PaperKnowledge] 正在创建知识库集合: {COLLECTION_NAME}")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
    finally:
        client.close()


def get_knowledge_store() -> QdrantVectorStore:
    global _knowledge_store
    if _knowledge_store is not None:
        return _knowledge_store

    _ensure_collection_exists()
    _knowledge_store = QdrantVectorStore.from_existing_collection(
        embedding=embeddings_model,
        collection_name=COLLECTION_NAME,
        url=QDRANT_CLOUDE_URL,
        api_key=_qdrant_api_key(),
    )
    return _knowledge_store


def build_paper_knowledge_documents(state: ResearchState, report: str) -> list[Document]:
    topic = state.get("topic", "未知主题")
    paper = state.get("current_source_paper", {}) or {}
    paper_title = paper.get("title", "未知论文")
    paper_url = paper.get("url") or paper.get("page_url", "")
    categories = paper.get("categories", [])
    arxiv_materials = state.get("arxiv_papers", [])
    multimodal_analysis = state.get("multimodal_analysis", "")
    screening_decision = paper.get("screening_decision", "")
    paper_id = _paper_id_from_metadata(paper)

    content = f"""
【论文知识架构】
研究主题: {topic}
论文标题: {paper_title}
论文链接: {paper_url}
Arxiv 分类: {", ".join(categories) if isinstance(categories, list) else categories}
AI 初筛结论: {screening_decision or "未记录"}

【核心方法与系统启发】
{_shorten(report, MAX_REPORT_CHARS)}

【图表/实验解析补充】
{_shorten(multimodal_analysis, MAX_CONTEXT_CHARS) or "无图表解析补充。"}

【原始论文材料摘要】
{_shorten(arxiv_materials, MAX_CONTEXT_CHARS)}
""".strip()

    base_metadata = {
        "paper_id": paper_id,
        "title": paper_title,
        "url": paper_url,
        "page_url": paper.get("page_url", ""),
        "topic": topic,
        "categories": categories,
        "published": paper.get("published", ""),
        "knowledge_type": "paper_core_architecture",
        "source_agent": "architect_agent",
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    chunks = _split_for_embedding(content)
    chunk_total = len(chunks)
    documents = []
    for index, chunk in enumerate(chunks):
        metadata = {
            **base_metadata,
            "chunk_index": index,
            "chunk_total": chunk_total,
        }
        documents.append(Document(page_content=chunk, metadata=metadata))

    return documents


def build_paper_knowledge_document(state: ResearchState, report: str) -> Document:
    documents = build_paper_knowledge_documents(state, report)
    if documents:
        return documents[0]
    return Document(page_content="", metadata={})


async def save_paper_knowledge(state: ResearchState, report: str) -> str:
    if not report or not report.strip():
        return "报告为空，未写入论文知识库。"

    documents = build_paper_knowledge_documents(state, report)
    if not documents:
        return "论文知识内容为空，未写入论文知识库。"

    paper_id = documents[0].metadata["paper_id"]
    point_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{paper_id}#{doc.metadata['chunk_index']}"))
        for doc in documents
    ]
    store = get_knowledge_store()
    await store.aadd_documents(documents, ids=point_ids)
    title = documents[0].metadata.get("title", "未知论文")
    return f"已写入论文知识库: {title}（{len(documents)} 个片段）"


async def search_paper_knowledge(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []

    store = get_knowledge_store()
    docs = await store.asimilarity_search(query, k=top_k)
    results = []
    for doc in docs:
        results.append(
            {
                "title": doc.metadata.get("title", "未知论文"),
                "url": doc.metadata.get("url", ""),
                "topic": doc.metadata.get("topic", ""),
                "published": doc.metadata.get("published", ""),
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
        )
    return results


async def retrieve_related_paper_knowledge(query: str, top_k: int = 3) -> str:
    try:
        results = await search_paper_knowledge(query, top_k=top_k)
    except Exception as e:
        print(f"[PaperKnowledge] 相关知识检索失败，已降级为空知识：{e}")
        return "无可用相关论文知识。"

    if not results:
        return "无可用相关论文知识。"

    blocks = []
    for index, result in enumerate(results, start=1):
        blocks.append(
            f"相关知识 {index}: {result['title']}\n"
            f"主题: {result.get('topic') or '未知'}\n"
            f"链接: {result.get('url') or '未记录'}\n"
            f"{_shorten(result['content'], MAX_CONTEXT_CHARS)}"
        )
    return "\n\n".join(blocks)
