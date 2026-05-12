import os
import sys
import json
import uuid
import asyncio
import traceback
from fastapi import Request
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from utils import append_reference_sections

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()


# 定义全局变量装载图谱
research_graph = None
AGENT_NODE_NAMES = {
    "arxiv_agent",
    "architect_agent",
    "supervisor",
    "human_supervisor_agent",
    "reviewer_agent",
    "multimodal_agent",
}
BUSY_RETRY_MESSAGE = "系统繁忙，请刷新后再试。"
BUSY_ERROR_KEYWORDS = (
    "429",
    "rate limit",
    "rate_limit",
    "too many requests",
    "限流",
    "网络波动",
    "requesterror",
    "connecterror",
    "readtimeout",
    "timeout",
    "timed out",
    "connection",
    "连接",
    "nodename nor servname",
    "temporarily unavailable",
    "多次重试后仍失败",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global research_graph
    from workflow.graph import create_research_workflow
    research_graph = await create_research_workflow()
    yield
    print("正在执行停机前的数据同步...")
    from memory.lessons import sync_lessons_to_cloud
    await sync_lessons_to_cloud()
    print("正在清理资源并关闭服务器...")

#初始化 FastAPI 应用
app = FastAPI(lifespan=lifespan)

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#路由与接口
@app.get("/")
async def get_index():
    # with open("index.html", "r", encoding="utf-8") as f:
    #     return HTMLResponse(f.read())
    return FileResponse("index.html")


def sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def compact_error_message(error: Exception | str) -> str:
    message = str(error).strip()
    if not message:
        return "未知错误"
    return message.splitlines()[-1][:800]


def is_busy_error(error: Exception | str) -> bool:
    message = str(error or "").lower()
    return any(keyword in message for keyword in BUSY_ERROR_KEYWORDS)


def user_facing_error_message(error: Exception | str) -> str:
    if is_busy_error(error):
        return BUSY_RETRY_MESSAGE
    return compact_error_message(error)


def workflow_failure_reason(values: dict) -> str:
    node_error = values.get("node_error")
    if node_error:
        return user_facing_error_message(node_error)

    feedback = str(values.get("review_feedback", "") or "")
    if "[SEARCH_FAILED]" in feedback:
        return BUSY_RETRY_MESSAGE
    if "[SEARCH_EXHAUSTED]" in feedback:
        return "当前关键词下没有找到新的可用论文，或者本地论文记录已全部读过。可以换一个研究主题，或清理已读论文记录后重试。"

    final_report = str(values.get("final_report", "") or "").strip()
    if not final_report and feedback not in ("[APPROVED]", "[EXIT]", "[ABORT]"):
        return "流程已结束，但没有生成可展示的报告。请查看节点历史，通常是检索、模型调用或论文解析阶段提前降级导致。"

    return ""


def workflow_finish_message(values: dict) -> str:
    feedback = str(values.get("review_feedback", "") or "")
    if "[EXIT]" in feedback or "[ABORT]" in feedback:
        return "流程已按用户要求中断"
    return "任务流转结束"


@app.get("/api/research")
async def stream_research(topic: str = "", thread_id: str = ""):
    """接收新主题或恢复旧的 thread_id"""
    
    async def event_generator():
        is_resume = bool(thread_id.strip())
        current_thread = thread_id.strip() if is_resume else str(uuid.uuid4())
        config = {"configurable": {"thread_id": current_thread}, "recursion_limit": 100}
        error_already_sent = False
        
        # 🌟 1. 第一时间把 Thread ID 发给前端，给前端吃定心丸
        yield sse_payload({'type': 'system', 'content': f'连接成功 | Thread ID: {current_thread}'})

        try:
            if research_graph is None:
                yield sse_payload({'type': 'error', 'content': '引擎尚未初始化完成，请稍后重试！'})
                return

            input_data = None if is_resume else {"topic": topic}
            
            async for event in research_graph.astream_events(input_data, config=config, version="v2"):
                kind = event["event"]
                
                #节点启动日志
                if kind == "on_chain_start":
                    node_name = event["name"]
                    if node_name in AGENT_NODE_NAMES:
                        yield sse_payload({'type': 'node', 'content': node_name})
                        
                elif kind == "on_chat_model_stream":
                    chunk_content = event["data"]["chunk"].content
                    if chunk_content:
                        yield sse_payload({'type': 'text', 'content': chunk_content})
                
                #节点结束判定
                elif kind == "on_chain_end":
                    node_name = event["name"]
                    node_output = event["data"].get("output", {})

                    if node_name in AGENT_NODE_NAMES and isinstance(node_output, dict):
                        if node_output.get("node_warning"):
                            yield sse_payload({
                                'type': 'warning',
                                'node': node_name,
                                'content': node_output.get("node_warning")
                            })

                        if node_output.get("node_error"):
                            error_already_sent = True
                            error_content = user_facing_error_message(node_output.get("node_error"))
                            yield sse_payload({
                                'type': 'error',
                                'node': node_name,
                                'content': error_content
                            })
                    
                    # 拦截人工审核节点，把生成的提纲交给前端，并触发挂起
                    if node_name == "human_supervisor_agent":
                        outline_text = node_output.get("outline", "") if isinstance(node_output, dict) else ""
                        report_text = node_output.get("final_report", "") if isinstance(node_output, dict) else ""
                        snapshot = await research_graph.aget_state(config)
                        report_text = append_reference_sections(report_text, snapshot.values)
                        response_data = {
                            'type': 'action_required', 
                            'thread_id': current_thread, 
                            'outline': outline_text, 
                            'full_report': report_text
                        }
                        yield sse_payload(response_data)

                elif kind == "on_custom_event" and event["name"] == "require_user_decision":
                    event_data = event["data"]
                    snapshot = await research_graph.aget_state(config)
                    report_text = append_reference_sections(event_data.get('full_report', ''), snapshot.values)
                    yield sse_payload({'type': 'action_required', 'thread_id': event_data.get('thread_id', current_thread), 'outline': event_data.get('outline', ''), 'full_report': report_text})

                elif kind in {"on_chain_error", "on_tool_error", "on_chat_model_error"}:
                    node_name = event.get("name", "unknown_node")
                    if node_name not in AGENT_NODE_NAMES:
                        continue

                    error_obj = event.get("data", {}).get("error", "未知节点异常")
                    error_already_sent = True
                    error_message = user_facing_error_message(error_obj)
                    yield sse_payload({
                        'type': 'error',
                        'node': node_name,
                        'content': error_message if error_message == BUSY_RETRY_MESSAGE else f"{node_name} 执行失败：{error_message}"
                    })

                pass
            
            await asyncio.sleep(0.1) # 确保 Redis 写入缓冲
            
            final_snapshot = await research_graph.aget_state(config)
            
            if len(final_snapshot.next) == 0:
                failure_reason = workflow_failure_reason(final_snapshot.values)
                if failure_reason:
                    yield sse_payload({
                        'type': 'error',
                        'content': failure_reason,
                        'full_report': append_reference_sections(
                            final_snapshot.values.get("final_report", ""),
                            final_snapshot.values
                        )
                    })
                    return

                final_report_content = append_reference_sections(
                    final_snapshot.values.get("final_report", ""),
                    final_snapshot.values
                )
                
                finish_data = {
                    'type': 'finish', 
                    'content': workflow_finish_message(final_snapshot.values),
                    'full_report': final_report_content
                }
                yield sse_payload(finish_data)
            else:
                print(f"图谱正在挂起等待，下一步将走向: {final_snapshot.next}")

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            if error_already_sent:
                return

            if "Received no input for __start__" in error_msg:
                print(f"\n检测到无效或已过期的 Thread ID: {current_thread}")
                friendly_message = "当前会话的记忆已在云端清理，请点击右上角【重新开始】开启全新任务。"
                yield sse_payload({'type': 'error', 'content': friendly_message})
            else:
                print(f"\n[系统异常]发生未知错误: {e}")
                error_message = user_facing_error_message(e)
                yield sse_payload({
                    'type': 'error',
                    'content': error_message if error_message == BUSY_RETRY_MESSAGE else f'系统异常: {error_message}'
                })

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/knowledge/search")
async def search_knowledge(query: str = "", limit: int = 5):
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "请输入要检索的知识问题。", "results": []}

    safe_limit = max(1, min(int(limit or 5), 10))
    try:
        from memory.paper_knowledge import search_paper_knowledge

        results = await search_paper_knowledge(query, top_k=safe_limit)
        return {"status": "ok", "query": query, "results": results}
    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"知识库检索失败: {compact_error_message(e)}",
            "results": [],
        }

@app.post("/api/decision")
async def submit_decision(request: Request):
    req_data = await request.json()
    thread_id = req_data.get("thread_id")
    decision = req_data.get("decision")
    feedback = req_data.get("feedback", "")
    
    if not thread_id:
        return {"status": "error", "message": "Missing thread_id"}

    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        state_updates = {}
        if decision == 'y':
            state_updates = {"next_node": "FINISH", "review_feedback": "[APPROVED]", "node_error": "", "node_warning": ""}
        elif decision == 'c':
            #退回搜索节点
            state_updates = {"next_node": "arxiv_agent", "review_feedback": "[CHANGE_PAPER]", "node_error": "", "node_warning": ""}
        elif decision == 'r':
            #退回Architect节点
            state_updates = {"next_node": "architect_agent", "review_feedback": f"[REWRITE] {feedback}", "node_error": "", "node_warning": ""}
        elif decision == 'n':
            state_updates = {"next_node": "FINISH", "review_feedback": "[ABORT]", "node_error": "", "node_warning": ""}

        await research_graph.aupdate_state(
            config=config,
            values=state_updates, 
            as_node="human_supervisor_agent" 
        )
        
        return {"status": "ok", "message": "Decision saved to Redis"}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
