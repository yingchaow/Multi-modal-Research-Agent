from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent

from state import ResearchState
from integrations.web_search import web_search_tool

model = ChatTongyi(model="qwen3-max")
web_search_react_agent = create_agent(model, [web_search_tool])

def web_search_agent_node(state: ResearchState):
    print("正在进行网页搜索，获取补充信息...")
    prompt = f"""
    请使用你的工具，检索关于“{state['topic']}”的最新进展、背景信息或相关概念解释。
    提炼出 2-3 个最重要的信息点或网站链接及其简要概括。
    注意：必须返回中文总结！
    """

    result = web_search_react_agent.invoke(
        {"messages": [HumanMessage(content=prompt)]}
    )
    final_answer = result["messages"][-1].content
    # 将网页搜索结果添加到状态中，这里假设是补充信息
    return {"web_search_results": [final_answer]}
