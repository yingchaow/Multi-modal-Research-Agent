from langchain_community.utilities import ArxivAPIWrapper
from langchain.tools import tool

class EnhancedArxivTool:
    def __init__(self, top_k_results=3, doc_content_chars_max=4000):
        # 实例化底层引擎，保持与原生 arxiv_tool 一致的参数
        self.wrapper = ArxivAPIWrapper(
            top_k_results=top_k_results, 
            doc_content_chars_max=doc_content_chars_max
        )

    def search(self, query: str) -> str:
        """执行搜索并返回包含 URL 的格式化字符串"""
        # 调用底层方法获取包含 metadata 的 Document 对象列表
        docs = self.wrapper.get_summaries_as_docs(query)
        
        if not docs:
            return "No relevant arxiv papers found."
            
        formatted_results = []
        for i, doc in enumerate(docs):
            # 从 metadata 中精准提取被原生工具丢弃的 Entry ID (即 URL)
            title = doc.metadata.get('Title', 'Unknown Title')
            url = doc.metadata.get('Entry ID', 'No URL available')
            authors = doc.metadata.get('Authors', 'Unknown Authors')
            published = doc.metadata.get('Published', 'Unknown Date')
            summary = doc.page_content
            
            # 重新组装成给大模型阅读的文本，显式包含真实链接
            paper_info = (
                f"【Paper {i+1}】\n"
                f"Title: {title}\n"
                f"URL: {url}\n"
                f"Authors: {authors}\n"
                f"Published: {published}\n"
                f"Summary: {summary}\n"
                f"{'-'*30}"
            )
            formatted_results.append(paper_info)
            
        return "\n".join(formatted_results)

# 使用装饰器将其转化为 Agent 可以识别的工具
@tool
def enhanced_arxiv_search(query: str) -> str:
    """
    Search Arxiv for scientific papers. 
    This tool returns paper titles, authors, summaries, AND the official source URLs.
    """
    tool_instance = EnhancedArxivTool()
    return tool_instance.search(query)