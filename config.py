import os
from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings

load_dotenv()

Qwen_API_KEY = os.getenv("ChatTongyi_API_KEY")
S2_API_KEY = os.getenv("S2_API_KEY")
VISION_MODEL_URL = os.getenv("vision_model_URL")
# QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_CLOUDE_URL = os.getenv("QDRANT_CLOUDE_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

if not REDIS_URL and REDIS_HOST == "redis" and not os.path.exists("/.dockerenv"):
    # docker-compose 内部使用 redis:6379；本机直接运行时连接宿主机映射端口。
    REDIS_HOST = "localhost"
    if REDIS_PORT == 6379:
        REDIS_PORT = 6380

vision_model = ChatTongyi(
    model="qwen-vl-max",
    base_url=VISION_MODEL_URL,
    dashscope_api_key=Qwen_API_KEY,
    verbose=True
)
architect_model = ChatTongyi(
    model="qwen-plus",
    streaming=True,
    dashscope_api_key=Qwen_API_KEY
)
human_supervisor_model = ChatTongyi(
    model="qwen-turbo",
    streaming=True,
    dashscope_api_key=Qwen_API_KEY
)
reviewer_model = ChatTongyi(
    model="qwen-plus",
    streaming=True,
    dashscope_api_key=Qwen_API_KEY
)
embeddings_model = DashScopeEmbeddings(
    model="text-embedding-v1",
    dashscope_api_key=Qwen_API_KEY
)
human_interaction_model = ChatTongyi(
    model="qwen-plus-2025-07-28",
    streaming=True,
    dashscope_api_key=Qwen_API_KEY
)
paper_filter_model = ChatTongyi(
    model="qwen-turbo",
    streaming=False,
    dashscope_api_key=Qwen_API_KEY,
)