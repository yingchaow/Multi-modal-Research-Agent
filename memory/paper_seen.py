import sqlite3
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "seen_papers.sqlite")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 论文记忆表
    c.execute('''
        CREATE TABLE IF NOT EXISTS seen_papers (
            arxiv_id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 【新增】主题探索深度表
    c.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            search_query TEXT PRIMARY KEY,
            max_offset INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def is_paper_seen(arxiv_id: str) -> bool:
    """检查论文是否已经被处理过"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM seen_papers WHERE arxiv_id = ?', (arxiv_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_paper_as_seen(arxiv_id: str, title: str, status: str = 'PROCESSED'):
    """将论文打上标记，存入记忆库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO seen_papers (arxiv_id, title, status) 
        VALUES (?, ?, ?)
    ''', (arxiv_id, title, status))
    conn.commit()
    conn.close()
    
def get_query_max_offset(search_query: str) -> int:
    """获取某个搜索词历史到达的最大深度"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT max_offset FROM search_history WHERE search_query = ?', (search_query,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_query_max_offset(search_query: str, new_offset: int):
    """更新某个搜索词的最大深度（只增不减）"""
    current_max = get_query_max_offset(search_query)
    if new_offset > current_max:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO search_history (search_query, max_offset) 
            VALUES (?, ?)
        ''', (search_query, new_offset))
        conn.commit()
        conn.close()

init_db()
