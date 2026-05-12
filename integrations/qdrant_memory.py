from qdrant_client import QdrantClient
from config import QDRANT_API_KEY, QDRANT_CLOUDE_URL

qdrant_client = QdrantClient(
    url=QDRANT_CLOUDE_URL, 
    api_key=QDRANT_API_KEY if QDRANT_CLOUDE_URL and QDRANT_CLOUDE_URL.startswith("https") else None,
    timeout=10.0
)

if __name__ == "__main__":
    print(qdrant_client.get_collections())
