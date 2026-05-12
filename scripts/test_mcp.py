# --- test_mcp.py ---
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_mcp_client():
    # 1. 配置你要启动的 Server (替换为你实际的虚拟环境 python 路径和脚本路径)
    # 注意：根据你上一轮的日志，你的路径应该是这样：
    server_params = StdioServerParameters(
        command="/Users/wang/Documents/cross_model_retrieval_multi_agent/.venv/bin/python",
        args=["/Users/wang/Documents/cross_model_retrieval_multi_agent/integrations/qdrant_mcp.py"]
    )

    print("🔄 正在启动并连接 Qdrant MCP Server...")
    
    # 2. 通过标准输入输出(stdio)连接 Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 必须先初始化
            await session.initialize()
            print("✅ 连接成功！")

            # 3. 看看 Server 提供了哪些工具
            tools_response = await session.list_tools()
            print("\n🛠️ 发现可用工具:")
            for tool in tools_response.tools:
                print(f"  - {tool.name}: {tool.description}")

            print("\n" + "="*40 + "\n")

            # 4. 真正调用工具！测试获取统计数据
            print("📊 正在调用工具: get_collection_stats...")
            result = await session.call_tool("get_collection_stats", arguments={})
            print(f"👉 结果: {result.content[0].text}")

            print("\n" + "="*40 + "\n")

            # 5. 测试语义搜索工具
            print("🔍 正在调用工具: search_papers_by_text...")
            search_result = await session.call_tool(
                "search_papers_by_text", 
                arguments={"query": "generative recommendation", "limit": 3}
            )
            print(f"👉 结果:\n{search_result.content[0].text}")

if __name__ == "__main__":
    asyncio.run(run_mcp_client())
