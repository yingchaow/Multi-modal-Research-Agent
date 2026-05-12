# from langchain.tools import tool
# from langchain_community.utilities import ArxivAPIWrapper

# @tool
# def arxiv_url_tool(query: str) -> str:
#     """
#     当你需要搜索 Arxiv 论文时，必须调用此工具。
#     输入参数：搜索关键词（如 "cross modal retrieval"）。
#     返回结果：包含论文标题、真实 URL 和摘要的文本。
#     """
#     arxiv = ArxivAPIWrapper(top_k_results=3, doc_content_chars_max=4000)
#     docs = arxiv.get_summaries_as_docs(query)

#     result_strings = []
#     for i, doc in enumerate(docs):
#         title = doc.metadata.get('Title', '未知标题')
#         # 最核心的一步：把被原生工具藏起来的 Entry ID 拿出来
#         real_url = doc.metadata.get('Entry ID', '无链接') 
#         summary = doc.page_content.replace('\n', ' ')
        
#         # 强制把 URL 拼接到大模型能看到的文本里
#         paper_info = (
#             f"【论文 {i+1}】\n"
#             f"标题: {title}\n"
#             f"真实URL: {real_url}\n"
#             f"摘要: {summary}\n" # 截断一下摘要防止 Token 超出
#             f"------------------------"
#         )
#         result_strings.append(paper_info)
        
#     # 将拼接好的字符串返回给大模型的“大脑”
#     return "\n".join(result_strings)

import re

def extract_github_links_as_markdown(papers_list: list[str]) -> str:
    """
    从论文纯文本列表中提取 GitHub 链接，并组装成 Markdown 格式的字符串。
    如果没有找到链接，则返回空字符串。
    """
    github_links = set()
    
    for paper_text in papers_list:
        # 匹配标准 GitHub 仓库链接
        pattern = r'https?://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9-_\.]+'
        links = re.findall(pattern, paper_text)
        
        for link in links:
            # 清理标点符号杂质
            clean_link = link.rstrip(".)],\"'")
            github_links.add(clean_link)
            
    if not github_links:
        return ""
        
    # 组装 Markdown
    github_section = "\n\n###论文中提及的开源代码\n"
    for link in github_links:
        github_section += f"- {link}\n"
        
    return github_section


def append_reference_sections(report_content: str, state_values: dict) -> str:
    """Append verified source/reference sections that are managed by the system."""
    if not report_content:
        return report_content

    final_report = report_content
    latest_paper = state_values.get('current_source_paper', {}) or {}
    github_section = state_values.get('GitHub_link_section', '')

    if latest_paper and latest_paper.get('url') and "参考原论文溯源" not in final_report:
        paper_url = latest_paper['url']
        paper_title = latest_paper.get('title', '未知标题')
        final_report += f"\n\n---\n**参考原论文溯源**: [{paper_title}]({paper_url})"

    if github_section and "###论文中提及的开源代码" not in final_report:
        final_report += github_section

    return final_report
