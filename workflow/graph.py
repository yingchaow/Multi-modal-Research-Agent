import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
import redis.asyncio as redis
# import redis
from state import ResearchState
from agent_nodes.arxiv_agent import arxiv_agent_node
from agent_nodes.architect_agent import architect_agent_node
from agent_nodes.supervisor_agent import supervisor_node
from agent_nodes.human_interaction_agent import human_interaction_agent_node
from agent_nodes.human_supervisor_agent import human_superviser_agent_node
from agent_nodes.reviewer_agent import reviewer_agent_node
from agent_nodes.multimodel_agent import multimodal_agent_node
from langchain_core.runnables.config import RunnableConfig
from langgraph.pregel.main import RetryPolicy
from config import QDRANT_API_KEY, REDIS_HOST, REDIS_PORT, REDIS_URL

# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def route_from_supervisor(state: ResearchState):
    """
    处理中心节点的路由分发。
    包含对 Reviewer 节点“换论文”请求的强力拦截。
    """
    feedback = state.get('review_feedback', "")
    
    if feedback == "[CHANGE_PAPER]":
        print("\n[图路由-Supervisor] 收到 Reviewer 换论文请求，立即调度 Arxiv 爬虫...")
        return "arxiv_agent"
        
    elif feedback == "[SEARCH_EXHAUSTED]":
        print("\n[图路由-Supervisor] 论文库已耗尽，被迫终止当前流程...")
        return "FINISH"
        
    return state.get('next_node', 'FINISH')


def route_after_human_supervisor(state: ResearchState):
    feedback = state.get('review_feedback', "")
    
    if feedback == "[APPROVED]" or feedback == "[EXIT]" or state.get('is_exit'):
        return "FINISH"
        
    elif feedback == "[CHANGE_EMPTY]" or feedback == "[CHANGE_PAPER]":
        print("\n[图路由-Human] 人类主管要求换论文，正在唤醒 Arxiv 爬虫...")
        return "arxiv_agent"
        
    elif feedback.startswith("[REWRITE]"):
        print("\n[图路由-Human] 人类主管要求大修，打回 Architect 原地重写...")
        return "architect_agent"
        
    return "FINISH"

async def create_research_workflow():
    workflow = StateGraph(ResearchState)
    
    retry_policy = RetryPolicy(
        initial_interval=2.0, 
        backoff_factor=2.0, 
        max_interval=10.0, 
        max_attempts=3
    )
    workflow.add_node("arxiv_agent", arxiv_agent_node, retry_policy=retry_policy)
    workflow.add_node("architect_agent", architect_agent_node, retry_policy=retry_policy)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("human_interaction_agent", human_interaction_agent_node, retry_policy=retry_policy)
    workflow.add_node("human_supervisor_agent", human_superviser_agent_node, retry_policy=retry_policy)
    workflow.add_node("reviewer_agent", reviewer_agent_node, retry_policy=retry_policy)
    workflow.add_node("multimodal_agent", multimodal_agent_node, retry_policy=retry_policy)
    
    workflow.add_edge(START, "human_interaction_agent") 
    workflow.add_edge("human_interaction_agent", "supervisor")
    workflow.add_edge("arxiv_agent", "supervisor")
    workflow.add_edge("multimodal_agent", "supervisor")
    workflow.add_edge("architect_agent", "supervisor")
    workflow.add_edge("reviewer_agent", "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "arxiv_agent": "arxiv_agent",
            "architect_agent": "architect_agent",
            "multimodal_agent": "multimodal_agent",
            "reviewer_agent": "reviewer_agent",
            "human_supervisor_agent": "human_supervisor_agent",
            "FINISH": END
        }
    )
    
    workflow.add_conditional_edges(
        "human_supervisor_agent",
        route_after_human_supervisor,
        {
            "FINISH": END,                        
            "architect_agent": "architect_agent",
            "arxiv_agent": "arxiv_agent"
        }
    )

    # memory_saver = AsyncRedisSaver.from_conn_info(host=REDIS_HOST, port=REDIS_PORT)


    # redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    redis_url = REDIS_URL or f"redis://{REDIS_HOST}:{REDIS_PORT}"
    memory_saver = AsyncRedisSaver(redis_url)
    
    await memory_saver.setup()
    
    print("已成功挂载 Redis 内存状态机")

    return workflow.compile(checkpointer=memory_saver)
