from state import ResearchState
"""
is_exit: none | false | true
"""
def supervisor_node(state: ResearchState):
    print("\n" + "="*50)
    print("[中心路由 Supervisor] 正在进行全局状态判定...")
    
    next_node = state.get('next_node', 'FINISH')
    is_exit = state.get('is_exit', None)
    feedback = state.get('review_feedback', '')
    final_report = state.get('final_report', '')
    final_destination = "FINISH"


    # 优先级 A：强制退出标识
    if is_exit:
        print("准备终止工作流。")
        final_destination = "FINISH"
        
    # 优先级 B：资源枯竭标识
    elif "[SEARCH_EXHAUSTED]" in feedback:
        print("论文库已耗尽，无可用数据，准备终止工作流。")
        final_destination = "FINISH"
        
    # 优先级 C：满意结束
    elif "[APPROVED]" in feedback:
        print("通过审核，准备生成最终报告并退出。")
        final_destination = "FINISH"
        
    # 优先级 D：换论文拦截 (Reviewer 或 Human 要求换论文，强制转给 Arxiv)
    elif "[CHANGE_PAPER]" in feedback or "[CHANGE_EMPTY]" in feedback:
        # print("收到换论文请求 [CHANGE_PAPER]，强制路由至 Arxiv 爬虫。")
        final_destination = "arxiv_agent"
        
    # 优先级 E：按子节点指定的 next_node 正常流转
    else:
        print(f"系统状态正常，按指令放行至 -> {next_node}")
        # print("is_exit:", is_exit)
        # print("review_feedback:", feedback[:20] + "..." if feedback else "无")
        # print("final_report:", final_report[:20] + "..." if final_report else "无")
        final_destination = next_node

    print("="*50)

    # 3. 将最终决定的去向覆写回状态，供图的条件边读取
    return {
        "next_node": final_destination
    }