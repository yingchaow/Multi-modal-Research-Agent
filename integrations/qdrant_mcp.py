# --- qdrant_mcp.py ---
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
import os

# 1. 初始化你的 MCP Server
mcp = FastMCP("MyQdrantKnowledgeBase")

# 2. 连接到你本地的 Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# 保持咱们之前修改的无 Key 本地连接逻辑
use_api_key = QDRANT_API_KEY if QDRANT_URL.startswith("https") else None
client = QdrantClient(url=QDRANT_URL, api_key=use_api_key)

COLLECTION_NAME = "paper_knowledge" 

# ==========================================
# 🌟 注册 MCP 工具 (Tools)
# 这些函数会被大模型直接发现并调用
# ==========================================

@mcp.tool()
async def search_papers_by_text(query: str, limit: int = 5) -> str:
    """
    语义检索工具：在本地知识库中搜索与查询主题最相关的论文。
    :param query: 用户的搜索提问 (例如："有什么好的多模态检索方法？")
    :param limit: 返回结果的最大数量
    """
    try:
        # 这里用了一个简化的检索逻辑（如果你有 embedding 模型，这里需要先做 embedding）
        # 如果你之前存数据的时候带了 payload (比如存了 abstract 和 title)
        # 我们可以通过纯文本匹配或向量匹配来找
        # 假设我们用最简单的 filter 或者你需要集成你的 embedding 逻辑
        
        # ⚠️ 注意：这里为了演示最简单的 MCP，假设你用 Qdrant 的原生查询。
        
        # 伪代码演示：返回格式化的字符串结果给大模型
        result_text = f"在 Qdrant 中搜索 '{query}' 的结果 (最多 {limit} 条):\n\n"
        result_text += "1. [SIGIR] 《Generative Recommendation with LLMs》\n"
        result_text += "2. [KDD] 《Cross-modal Retrieval using Contrastive Learning》\n"
        
        return result_text
    except Exception as e:
        return f"检索失败: {str(e)}"

@mcp.tool()
async def get_collection_stats() -> str:
    """
    统计工具：获取当前知识库(Qdrant)中的论文总数。
    """
    try:
        count_result = client.count(collection_name=COLLECTION_NAME)
        return f"当前知识库 '{COLLECTION_NAME}' 中共存储了 {count_result.count} 篇文献或教训。"
    except Exception as e:
        return f"获取统计信息失败: {str(e)}"

if __name__ == "__main__":
    print("🚀 Qdrant MCP Server 准备启动...")
    # 启动 MCP 服务，使用 stdio 协议 (Cursor 和 Claude 最喜欢的通信方式)
    mcp.run()
