import os
# from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import HumanMessage
from memory.lessons import save_lesson_to_memory
from state import ResearchState
# from config import Qwen_API_KEY
from config import reviewer_model
# load_dotenv()  # 加载 .env 文件中的环境变量

# api_key = os.getenv("ChatTongyi_API_KEY")  # 从环境变量中获取

# model = ChatTongyi(
#     model="qwen-plus",
#     streaming=True,
#     api_key=Qwen_API_KEY
# )
model = reviewer_model
async def reviewer_agent_node(state: ResearchState):
    print("\n[Reviewer] 正在进行第 {} 次 AI 评审...".format(state.get('review_retry_count', 0) + 1))
    
    retry_count = state.get('review_retry_count', 0)
    topic = state.get('topic', '未知主题')
    content = ""
    report = state.get('final_report', '没有报告可供评审。')
    current_paper = state.get('current_source_paper', {}) or {}
    papers_list = state.get('arxiv_papers', [])
    papers_content = "\n\n".join(papers_list) if isinstance(papers_list, list) else str(papers_list)
    multimodal_analysis = state.get('multimodal_analysis', '')
    paper_meta_text = "\n".join(
        f"{key}: {value}" for key, value in current_paper.items() if value
    ) or "无"

    prompt = f"""
    你是一位严谨且务实的顶会审稿人（Reviewer Agent）。你的任务是评估当前报告是否基于给定论文材料，产出了一份对研究主题“{topic}”有参考价值的技术调研报告。
    你既要拒绝明显跑题或捏造信息的报告，也要允许“材料有限但忠实、结构清楚、启发明确”的报告通过。

    【当前论文元信息】
    {paper_meta_text}

    【原始真实研究资料】
    {papers_content}

    【论文图表解析】
    {multimodal_analysis or "无图表解析或解析失败"}
    
    【报告初稿内容】
    {report}
    
    【评审标准】
    1. 主题相关性：论文与“{topic}”在任务目标、方法范式、数据处理、评估方式或系统设计上至少有一个清晰关联，即可认为有保留价值。
    2. 证据忠实度：报告不得编造输入材料中没有的公式、实验数值、数据集、开源链接或结论；如果材料未披露，报告应明确说明。
    3. 报告质量：报告应包含背景定位、核心方法/技术启发、实验或证据边界、局限与后续方向。若原始材料只给摘要，不应强制要求报告写出具体公式或实验数值。
    4. 改写优先：如果论文本身相关，但报告缺少结构、证据边界或技术启发，请给 [REWRITE]，不要直接 [CHANGE_PAPER]。
    
    【标尺基准】
    - [通过基准]：论文研究的是医疗图像分割，而我们的主题是卫星图像分割。虽然领域不同，但都用到了最新的扩散模型，具有极强的技术借鉴意义。 -> 应当保留。
    - [拒绝基准]：我们的主题是“大模型推理优化”，而这篇论文只是用 ChatGPT 写了一篇关于心理学的调研报告。 -> 毫无技术关联，必须拒绝。

    【输出格式要求】
    你的回答必须包含 <thinking> 过程，并且最后一行严格以以下三个标签之一开头：

    <thinking>
    1. 分析论文与“{topic}”的真实关联度。
    2. 分析报告是否忠实使用材料，是否把核心价值和证据边界写清楚。
    </thinking>

    [APPROVED_AI] 论文有参考价值，且报告忠实、结构完整、技术启发清楚，建议通过。
    [REWRITE] 论文有价值，但当前报告需要重写或补充。请明确指出下一个节点应修复的具体问题。
    [CHANGE_PAPER] 论文方向严重不符或关联极度牵强，理由是：[简述理由]，要求换篇新论文。
    """
    
    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        node_error = ""
    except Exception as e:
        print(f"[Reviewer] 大模型调用失败: {e}")
        content = "[REWRITE] 评审节点发生网络异常，请架构师自我检查并重新生成。"
        node_error = ""
        node_warning = f"Reviewer 评审模型调用失败，已转为重写建议继续流程：{e}"
    else:
        node_warning = ""

    if "[APPROVED_AI]" in content:
        print("[Reviewer] 评审通过！移交人类主管。")
        return {
            "next_node": "human_supervisor_agent",
            "review_feedback": content,
            "review_retry_count": 0,  # 成功后重置计数器
            "node_error": node_error,
            "node_warning": node_warning,
        }
    
    new_retry_count = retry_count + 1
    
    if new_retry_count >= 3:
        print(f"[Reviewer]已连续失败 {new_retry_count} 次，触发【自动降级】，移交人类主管决策。")
        content = "[REWRITE]"
        return {
            "next_node": "human_supervisor_agent",
            "review_feedback": content,
            "review_retry_count": 0,
            "node_error": node_error,
            "node_warning": node_warning,
        }
    else:
        
        if "[CHANGE_PAPER]" in content:
            # print(CHANGE_PAPER)
            # content = "[CHANGE_PAPER]"
            # print (content)
            print("[Reviewer] 发现论文严重跑题，强制要求更换论文！")
        # return {"next_node": "supervisor", "review_feedback": content}
        else:
            print("[Reviewer] 评审未通过，打回架构师重写。")
            # content = "[REWRITE]"
            if "[REWRITE]" in content:
                clean_feedback = content.replace("[REWRITE]", "").strip()
                await save_lesson_to_memory(topic=topic, feedback=clean_feedback, source="ai_reviewer")
            
            # print(f"[Reviewer] 评审未通过，当前第 {new_retry_count} 次尝试，打回架构师重写。")
        
        # clean_feedback = content.replace("[REWRITE]", "").strip()
        # await save_lesson_to_memory(topic=topic, feedback=clean_feedback, source="ai_reviewer")
        
        return {
            "next_node": "architect_agent",
            "review_feedback": content,
            "review_retry_count": new_retry_count,
            "is_exit": False,
            "node_error": node_error,
            "node_warning": node_warning,
        }
    
if __name__ == "__main__":
    test = model.invoke("你是什么模型？")
    print(test.content)
