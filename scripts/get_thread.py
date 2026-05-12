import sqlite3

# 连接到你的数据库
conn = sqlite3.connect("research_checkpoints.sqlite")
cursor = conn.cursor()

# 查询最新的一条 thread_id
cursor.execute("SELECT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1")
result = cursor.fetchone()

if result:
    print(f"🔍 最后一次运行的 Thread ID 是: {result[0]}")
else:
    print("📭 数据库目前是空的，没有找到任何记录。")

conn.close()