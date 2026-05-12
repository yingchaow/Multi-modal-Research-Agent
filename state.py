from typing import TypedDict, Union, List
# import config


class ResearchState(TypedDict):
    topic: str                 # 给大模型写报告用的中文主题
    english_topic: str         # 【新增】专门喂给 Arxiv 爬虫的英文检索词
    search_keywords: list[str] # Arxiv 检索关键词拆分结果
    # search_offset: int = config.count        
    current_source_paper: dict 
    arxiv_papers: list[str]    
    web_search_results: list[str] 
    final_report: str          
    review_feedback: str       
    next_node: str             
    is_exit: bool
    review_retry_count: int
    multimodal_analysis: str
    GitHub_link_section: str
    node_error: str
    node_warning: str
