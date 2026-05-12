import os
import re
import asyncio
from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.runnables.config import RunnableConfig # 确保导入了 RunnableConfig
from state import ResearchState
from memory.lessons import save_lesson_to_memory
from core import session_store
from utils import append_reference_sections
# from config import Qwen_API_KEY
from config import human_supervisor_model
# load_dotenv()  # 加载 .env 文件中的环境变量
# api_key = os.getenv("ChatTongyi_API_KEY")  # 从环境变量中获取
# model = ChatTongyi(
#     model="qwen-turbo",
#     streaming=True,
#     api_key=Qwen_API_KEY
# )
model = human_supervisor_model

async def human_superviser_agent_node(state: ResearchState, config: RunnableConfig):
    print("\n" + "="*50)
    print("人工审核代理节点 (正在为您生成报告提纲...) ")
    print("="*50)
    
    report = append_reference_sections(
        state.get('final_report', '报告尚未生成。'),
        state
    )

    outline = ""
    if report and report != '报告尚未生成。':
        prompt = f"""
        你是一个专业的学术助理。请将以下这份完整的研究报告浓缩成一份【500字以内】的核心提纲。
        提纲需要包含报告的“核心背景”、“主要结论”和“关键结构”，方便人类主管快速审阅和决策。
        
        研究报告原文：
        {report}
        """
        try:
            response = await model.ainvoke([HumanMessage(content=prompt)])
            outline = response.content.strip()
        except Exception as e:
            outline = f"生成提纲失败，直接显示前500字: \n{report[:500]}..."
    else:
        outline = "报告为空，无法生成提纲。"
        
    # print(outline)

    thread_id = config.get("configurable", {}).get("thread_id", "default")
    dispatch_custom_event("require_user_decision", {
        "thread_id": thread_id,
        "outline": outline,
        "full_report": report
    })
    print("\n[挂起] 提纲生成完毕，正在等待网页端人类主管决策...")

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    session_store.user_decisions[thread_id] = future
    
    decision_data = await future 
    
    user_decision = decision_data.get("decision")
    human_advice = decision_data.get("feedback", "").strip()

    
    if thread_id in session_store.user_decisions:
        del session_store.user_decisions[thread_id]

    print("\n" + "-"*50)
    if user_decision == 'y':
        print("主管已在网页端批准！正在准备生成最终文档...")
        return {
            "next_node": "FINISH", 
            "review_feedback": "[APPROVED]",
            "is_exit": False,
            "node_error": "",
            "node_warning": "",
        }
        
    elif user_decision == 'r':
        topic = state.get('topic', '未知主题')
        
        if not human_advice:
            human_advice = "人工主管审阅提纲后认为报告仍需完善，请全面检查质量并重写。"
            
        await save_lesson_to_memory(topic=topic, feedback=human_advice, source="human_supervisor")
        print(f"主管在网页端打回重写。附带意见: {human_advice}")
        return {
            "next_node": "architect_agent", 
            "review_feedback": f"[REWRITE] {human_advice}",
            "is_exit": False,
            "node_error": "",
            "node_warning": "",
        }
        
    elif user_decision == 'c':
        print("主管在网页端判定论文不符，正在呼叫 Arxiv 爬虫极速抓取下一篇...")
        return {
            "next_node": "arxiv_agent", 
            "review_feedback": "[CHANGE_PAPER]",
            "is_exit": False,
            "node_error": "",
            "node_warning": "",
        }
        
    else: 
        print("主管在网页端强制退出流程。")
        return {
            "next_node": "FINISH", 
            "review_feedback": "[EXIT]",
            "is_exit": True,
            "node_error": "",
            "node_warning": "",
        }
    
if __name__ == "__main__":
    async def test():
        test_res = await model.ainvoke([HumanMessage(content="你是什么模型？")])
        print(test_res.content)
    asyncio.run(test())
