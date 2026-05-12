
import os
from typing import List

from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models
from config import QDRANT_CLOUDE_URL, embeddings_model, QDRANT_API_KEY

# load_dotenv()

# 强制清理代理，确保云端连接稳定
os.environ['NO_PROXY'] = '*'
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    os.environ.pop(key, None)

QDRANT_URL = QDRANT_CLOUDE_URL
qdrant_api_key = QDRANT_API_KEY
COLLECTION_NAME = "architect_lessons"

_local_lessons_buffer: List[Document] = []
_memory_store: QdrantVectorStore | None = None


def _qdrant_api_key() -> str | None:
    if QDRANT_URL and QDRANT_URL.startswith("https"):
        return qdrant_api_key
    return None

def ensure_collection_exists():
    """同步检查集合是否存在"""
    if not QDRANT_URL:
        raise RuntimeError("Qdrant 配置缺失：请检查 QDRANT_CLOUDE_URL。")

    sync_client = QdrantClient(
        url=QDRANT_URL, 
        api_key=_qdrant_api_key(),
        timeout=5,
        check_compatibility=False,
    )    
    try:
        if not sync_client.collection_exists(COLLECTION_NAME):
            print(f"正在云端创建集合: {COLLECTION_NAME}...")
            sync_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
            )
            print("集合创建成功！")
    finally:
        sync_client.close()


def get_memory_store() -> QdrantVectorStore:
    global _memory_store
    if _memory_store is not None:
        return _memory_store

    ensure_collection_exists()
    _memory_store = QdrantVectorStore.from_existing_collection(
        embedding=embeddings_model,
        collection_name=COLLECTION_NAME,
        url=QDRANT_URL,
        api_key=_qdrant_api_key(),
    )
    return _memory_store

async def save_lesson_to_memory(topic: str, feedback: str, source: str = "human_supervisor"):
    """
    存入本地缓冲区
    """
    if not feedback or not feedback.strip():
        return
        
    doc = Document(
        page_content=feedback,
        metadata={"topic": topic, "source": source}
    )
    
    # 存入本地内存列表
    _local_lessons_buffer.append(doc)
    
    print(f"[本地缓冲] 已记录教训。当前缓冲区待上传数量: {len(_local_lessons_buffer)}")

async def retrieve_past_lessons(current_topic: str, top_k: int = 2) -> str:
    """从云端检索历史经验"""
    print(f"正在从云端检索与 '{current_topic}' 相关的历史经验...")
    
    # 异步检索
    docs = await get_memory_store().asimilarity_search(current_topic, k=top_k)
    
    if not docs:
        return ""
    
    lessons = "\n".join([f"经验 {i+1}: {doc.page_content}" for i, doc in enumerate(docs)])
    return lessons

async def sync_lessons_to_cloud():
    """
    批量上传本地缓冲区内容到云端
    """
    global _local_lessons_buffer
    if not _local_lessons_buffer:
        print("缓冲区为空，无需同步。")
        return

    count = len(_local_lessons_buffer)
    print(f"正在将 {count} 条教训批量上传至 Qdrant Cloud...")
    
    try:
        # 使用批量添加，通过一次网络往返完成所有数据存储
        await get_memory_store().aadd_documents(_local_lessons_buffer)
        print(f"成功同步 {count} 条数据到云端向量库")
        _local_lessons_buffer = [] # 清空缓冲区
    except Exception as e:
        print(f"同步失败: {e}。数据仍保留在本地缓冲区中。")
