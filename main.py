import os
import sys
import uuid
import argparse
import traceback
import time
import asyncio
# 添加项目根目录到搜索路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import phoenix as px
from phoenix.otel import register # 新增导入
from openinference.instrumentation.langchain import LangChainInstrumentor

# 1. 启动本地服务器
session = px.launch_app()

# 2. 注册 OpenTelemetry 路由，让探针知道往哪里发数据
tracer_provider = register() 

# 3. 挂载探针，并绑定刚刚注册的路由
LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
print(f"Phoenix 追踪平台已启动: {session.url}")
from workflow.graph import create_research_workflow

async def process_stream(app, input_data, config):
    async for event in app.astream_events(input_data, config, version = "v2"):
        kind = event["event"]

        if kind == "on_chain_start":
            node_name = event["name"]
            # 过滤掉底层繁杂的内部组件，只显示我们在 Graph 中定义的节点
            if node_name in ["arxiv_agent", "architect_agent", "supervisor", 
                             "human_interaction_agent", "human_supervisor_agent", 
                             "reviewer_agent", "multimodal_agent"]:
                print(f"\n\n[节点流转] 当前正在执行: {node_name}")
            
        elif kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                print(content, end="", flush=True)    


async def async_main(args):
    app = await create_research_workflow()
    
    topic = "" # 研究主题将由 human_interaction_agent_node 从用户输入中获取
    
    # 如果命令行提供了 thread_id，则使用它；否则生成一个新的
    if args.thread_id:
        thread_id = args.thread_id
        topic = None
        print(f"Resuming research for topic: '{topic}' with provided thread_id: {thread_id}")
    else:
        # 生成一个唯一的会话ID，用于持久化和恢复状态
        thread_id = str(uuid.uuid4())
        print(f"Starting NEW research for topic: '{topic}' with generated thread_id: {thread_id}")
    
    # LangGraph 使用 'configurable' 键下的 'thread_id' 来标识不同的执行路径
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}

    # ================= 新增：全局重试机制配置 =================
    MAX_RETRIES = 3
    retry_count = 0
    is_completed = False
    # ==========================================================

    # 最外层重试循环
    # 最外层重试循环
    while retry_count <= MAX_RETRIES:
        
        is_completed = False

        try:
            graph_state = await app.aget_state(config)
            
            if not graph_state.values and not args.thread_id:
                # current_state = app.invoke({"topic": topic}, config=config)
                await process_stream(app, {"topic": topic}, config)
            elif graph_state.next:
                if retry_count > 0:
                    print(f"\n--- 从异常断点处恢复工作流，前往节点: {graph_state.next} ---")
                # current_state = app.invoke(None, config=config)
                await process_stream(app, None, config)

            # 内层循环：处理图的挂起恢复
            while True:
                graph_state = await app.aget_state(config)
                
                if not graph_state.next:
                    is_completed = True
                    break

                # 【重大变动】删除了这里拦截 architect_agent 的代码，全部交由 human_superviser_agent 控制
                print(f"\n--- 正在流转，前往节点: {graph_state.next} ---")
                # current_state = app.invoke(None, config=config) 
                await process_stream(app, None, config)


            if is_completed:
                break

        except Exception as e:
            retry_count += 1
            print(f"\n[异常捕获] 图节点执行出错: {e}")
            traceback.print_exc()
            if retry_count <= MAX_RETRIES:
                print(f"--- 启动重试机制 ({retry_count}/{MAX_RETRIES}) ---")
                await asyncio.sleep(3)
                # time.sleep(3)
            else:
                print(f"\n[致命错误] 已达到最高重试次数 ({MAX_RETRIES})。Thread ID: {thread_id}")
                break 

    # ================= 当图彻底跑完（is_completed = True）后的最终处理 =================
    if is_completed:
        final_state = (await app.aget_state(config)).values
        print("\n" + "="*50)
        print("✨ 研究任务工作流结束。")
        
        feedback = final_state.get('review_feedback', '')
        github_section = final_state.get('GitHub_link_section', '')
                
        # 1. 检查是否是异常中止或人类强制退出
        if "[EXIT]" in feedback or final_state.get('is_exit') or "[SEARCH_EXHAUSTED]" in feedback:
            print("任务已中止（或关键词耗尽），未生成/保存最终本地文件。")
            
        # 2. 只有在带有 [APPROVED] 标签时，才执行完美的本地保存
        elif "[APPROVED]" in feedback:
            report_content = final_state.get('final_report', '')
            if report_content and report_content != '报告尚未生成。':
                
                # 提取并追加论文真实的 URL 溯源链接
                latest_paper = final_state.get('current_source_paper', {})
                if latest_paper and latest_paper.get('url'):
                    last_url = latest_paper['url']
                    last_title = latest_paper.get('title', '未知标题')
                    print(last_title)
                    print("\n")
                    print(last_url)
                    report_content += f"\n\n---\n**参考原论文溯源**: [{last_title}]({last_url})"

                if github_section:
                    report_content += github_section
                
                # 执行绝对路径与 UUID 安全保存
                SAVE_DIR = "/Users/wang/Documents/cross_model_retrieval_multi_agent/papers"
                os.makedirs(SAVE_DIR, exist_ok=True)
                
                save_id = thread_id[:8]
                safe_topic_name = str(final_state.get('topic', '研究报告')).replace(' ', '_').replace('/', '')
                file_name = f"最终报告_{safe_topic_name}_{save_id}.txt"
                file_path = os.path.join(SAVE_DIR, file_name)
                
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                    print(f"完整报告已成功保存至: {file_path}")
                except Exception as e:
                    print(f"报告保存失败: {e}")
            else:
                print("没有检测到最终报告内容，未保存文件。")
        else:
            print("任务结束，但未获得明确的 [APPROVED] 批准指令，文件未保存。")
                
        print(f"对应的会话ID为: {thread_id}")
        print("="*50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run cross-model retrieval multi-agent research workflow.")
    parser.add_argument("--thread_id", type=str, help="Optional: Specify a thread ID to resume a previous session.")
    args = parser.parse_args()

    # Create and compile the research workflow defined in graph.py
    # app = create_research_workflow()

    # topic = "" # 研究主题将由 human_interaction_agent_node 从用户输入中获取
    
    # # 如果命令行提供了 thread_id，则使用它；否则生成一个新的
    # if args.thread_id:
    #     thread_id = args.thread_id
    #     topic = None
    #     print(f"Resuming research for topic: '{topic}' with provided thread_id: {thread_id}")
    # else:
    #     # 生成一个唯一的会话ID，用于持久化和恢复状态
    #     thread_id = str(uuid.uuid4())
    #     print(f"Starting NEW research for topic: '{topic}' with generated thread_id: {thread_id}")
    
    # # LangGraph 使用 'configurable' 键下的 'thread_id' 来标识不同的执行路径
    # config = {"configurable": {"thread_id": thread_id}}

    # # ================= 新增：全局重试机制配置 =================
    # MAX_RETRIES = 3
    # retry_count = 0
    # is_completed = False
    # # ==========================================================

    # # 最外层重试循环
    # # 最外层重试循环
    # while retry_count <= MAX_RETRIES:
        
    #     is_completed = False

    #     try:
    #         graph_state = app.get_state(config)
            
    #         if not graph_state.values and not args.thread_id:
    #             current_state = app.invoke({"topic": topic}, config=config)
    #         elif graph_state.next:
    #             if retry_count > 0:
    #                 print(f"\n--- 从异常断点处恢复工作流，前往节点: {graph_state.next} ---")
    #             current_state = app.invoke(None, config=config)

    #         # 内层循环：处理图的挂起恢复
    #         while True:
    #             graph_state = app.get_state(config)
                
    #             if not graph_state.next:
    #                 is_completed = True
    #                 break

    #             # 【重大变动】删除了这里拦截 architect_agent 的代码，全部交由 human_superviser_agent 控制
    #             print(f"\n--- 正在流转，前往节点: {graph_state.next} ---")
    #             current_state = app.invoke(None, config=config) 

    #         if is_completed:
    #             break

    #     except Exception as e:
    #         retry_count += 1
    #         print(f"\n[异常捕获] 图节点执行出错: {e}")
    #         traceback.print_exc()
    #         if retry_count <= MAX_RETRIES:
    #             print(f"--- 启动重试机制 ({retry_count}/{MAX_RETRIES}) ---")
    #             time.sleep(3)
    #         else:
    #             print(f"\n[致命错误] 已达到最高重试次数 ({MAX_RETRIES})。Thread ID: {thread_id}")
    #             break 

    # # ================= 当图彻底跑完（is_completed = True）后的最终处理 =================
    # if is_completed:
    #     final_state = app.get_state(config).values
    #     print("\n" + "="*50)
    #     print("✨ 研究任务工作流结束。")
        
    #     feedback = final_state.get('review_feedback', '')
    #     github_section = final_state.get('GitHub_link_section', '')
                
    #     # 1. 检查是否是异常中止或人类强制退出
    #     if "[EXIT]" in feedback or final_state.get('is_exit') or "[SEARCH_EXHAUSTED]" in feedback:
    #         print("任务已中止（或关键词耗尽），未生成/保存最终本地文件。")
            
    #     # 2. 只有在带有 [APPROVED] 标签时，才执行完美的本地保存
    #     elif "[APPROVED]" in feedback:
    #         report_content = final_state.get('final_report', '')
    #         if report_content and report_content != '报告尚未生成。':
                
    #             # 提取并追加论文真实的 URL 溯源链接
    #             latest_paper = final_state.get('current_source_paper', {})
    #             if latest_paper and latest_paper.get('url'):
    #                 last_url = latest_paper['url']
    #                 last_title = latest_paper.get('title', '未知标题')
    #                 report_content += f"\n\n---\n**参考原论文溯源**: [{last_title}]({last_url})"

    #             if github_section:
    #                 report_content += github_section
                
    #             # 执行绝对路径与 UUID 安全保存
    #             SAVE_DIR = "/Users/wang/Documents/cross_model_retrieval_multi_agent/papers"
    #             os.makedirs(SAVE_DIR, exist_ok=True)
                
    #             save_id = thread_id[:8]
    #             safe_topic_name = str(final_state.get('topic', '研究报告')).replace(' ', '_').replace('/', '')
    #             file_name = f"最终报告_{safe_topic_name}_{save_id}.txt"
    #             file_path = os.path.join(SAVE_DIR, file_name)
                
    #             try:
    #                 with open(file_path, 'w', encoding='utf-8') as f:
    #                     f.write(report_content)
    #                 print(f"完整报告已成功保存至: {file_path}")
    #             except Exception as e:
    #                 print(f"报告保存失败: {e}")
    #         else:
    #             print("没有检测到最终报告内容，未保存文件。")
    #     else:
    #         print("任务结束，但未获得明确的 [APPROVED] 批准指令，文件未保存。")
                
    #     print(f"对应的会话ID为: {thread_id}")
    #     print("="*50)
    asyncio.run(async_main(args))
    print("\n链路追踪数据已生成！")
    print(f"请在浏览器中刷新并查看: {session.url}")
    try:
        # 使用 input 阻塞程序退出。看完网页上的分析数据后，在终端按回车即可退出。
        input("\n[程序已暂停] 按回车键 (Enter) 关闭服务器并退出程序...")
    except KeyboardInterrupt:
        pass
    finally:
        # ================= 🌟 核心修改 2：给数据一点传输时间 =================
        print("\n正在导出最终追踪数据至大盘，请稍候...")
        time.sleep(3) # 强制休眠3秒，确保内存中的 Trace 批次全部发送完毕
        print("正在关闭 Phoenix 服务器...")
        px.close_app()
        print("工作流彻底结束。")
