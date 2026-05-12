import sqlite3

# 你的数据库路径
db_path = "research_checkpoints.sqlite"

def get_latest_thread_id():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 在 LangGraph 的 checkpoints 表中按最后更新时间排序
    # 注意：表名通常是 checkpoints
    try:
        query = "SELECT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1"
        cursor.execute(query)
        result = cursor.fetchone()
        if result:
            print(f"最后一次运行的 Thread ID 是: {result[0]}")
        else:
            print("数据库中没有找到记录。")
    except Exception as e:
        print(f"查询失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    get_latest_thread_id()