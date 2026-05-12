# import os
# from langchain_community.chat_models import ChatTongyi
# from langchain_core.messages import HumanMessage, SystemMessage
# from langgraph.graph import StateGraph, START, END
# from typing import Annotated, List, TypedDict
# from typing_extensions import TypedDict
# import operator
# from langchain_community.tools import ArxivQueryRun
# from langchain.agents import create_agent

# model = ChatTongyi(model="qwen3-max")

# class ResearchState(TypedDict):
#     topic: str
#     arxiv_papers: Annotated[List[str], operator.add]
#     final_report: str
#     next_node: str

# arxiv_tool = ArxivQueryRun()

# arxiv_react_agent = create_agent(model, [arxiv_tool])

# def arxiv_agent_node(state: ResearchState):
#     print("查询arxiv，获取相关论文...")
#     prompt = f"""
#     请使用你的工具，检索关于“{state['topic']}”的最新论文。
#     你需要阅读检索到的摘要，并提炼出 2-3 篇最具代表性的论文信息。
#     包括：论文标题、作者、核心摘要和结论。
#     注意：必须返回中文翻译的总结！
#     """

#     result = arxiv_react_agent.invoke(
#         {
#             "messages": [HumanMessage(content=prompt)]
#         }
#     )
#     final_answer = result["messages"][-1].content
#     return {"arxiv_papers": [final_answer]}

# def archetect_agent_node(state: ResearchState):
#     print("正在撰写研究报告...")

#     papers_content = "\n\n".join(state.get('arxiv_papers', []))
#     prompt = f"""
#     你是一位资深的 AI 架构师。请根据以下论文检索资料，撰写一份结构清晰的技术调研报告。
#     调研主题：{state['topic']}
    
#     要求：
#     1. 使用 Markdown 格式。
#     2. 包含“背景”、“核心研究进展”、“总结”三个部分。
#     3. 语言要专业、流畅。
    
#     参考文献资料如下：
#     {papers_content}
#     """

#     response = model.invoke([HumanMessage(content=prompt)])
#     print("研究报告撰写完成。")
#     return {"final_report": response.content}

# def supervisor_node(state: ResearchState):
#     print("正在审核研究报告...")
   
#     has_papers = len(state.get('arxiv_papers', [])) > 0
#     has_report = state.get('final_report') is not None

#     prompt = f"""
#     你是一个科研项目的主管。任务目标：{state['topic']}
    
#     当前状态：
#     - 是否已获取论文数据: {'是' if has_papers else '否'}
#     - 是否已生成最终报告: {'是' if has_report else '否'}
    
#     请严格根据以下规则决定下一步分配给谁：
#     1. 如果没有论文数据，输出：arxiv_agent
#     2. 如果有了论文数据，但还没生成报告，输出：architect_agent
#     3. 如果报告已经生成，输出：FINISH
    
#     注意：你的回复只能是这三个词语之一，不要带任何标点或额外文字。
#     """

#     response = model.invoke([SystemMessage(content=prompt)])
#     decision = response.content.strip()
#     print(f"主管决策：{decision}")
#     return {"next_node": decision}


# workflow = StateGraph(ResearchState)

# workflow.add_node("arxiv_agent", arxiv_agent_node)
# workflow.add_node("architect_agent", archetect_agent_node)
# workflow.add_node("supervisor", supervisor_node)

# workflow.add_edge(START, "supervisor")

# workflow.add_edge("arxiv_agent", "supervisor")
# workflow.add_edge("architect_agent", "supervisor")

# workflow.add_conditional_edges(
#     "supervisor",
#     lambda state: state['next_node'],
#     {
#         "arxiv_agent": "arxiv_agent",
#         "architect_agent": "architect_agent",
#         "FINISH": END
#     }
# )

# app = workflow.compile()

# if __name__ == "__main__":

#     topic = "噪声标签下的跨模态检索"
#     final_state = app.invoke({"topic": topic})
#     print("最终研究报告：", final_state.get('final_report', '没有生成报告'))
