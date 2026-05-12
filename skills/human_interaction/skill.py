import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from state import ResearchState


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompt_template.md")
DEFAULT_TOPIC = "跨模态检索"


class HumanInteractionSkill:
    """Convert user topics into Arxiv-ready English search keywords."""

    name = "human_topic_to_arxiv_query"

    async def arun(self, state: ResearchState, model: Any) -> dict[str, Any]:
        user_topic = self.normalize_topic(state.get("topic", ""))

        if not user_topic:
            print(f"未输入主题，使用默认主题：'{DEFAULT_TOPIC}'")
            user_topic = DEFAULT_TOPIC

        try:
            response = await model.ainvoke([HumanMessage(content=self.build_prompt(user_topic))])
            keywords, model_query = self.parse_keyword_response(response.content)
            if not keywords:
                keywords = [user_topic]

            english_topic = self.build_arxiv_query(keywords, model_query or user_topic)
            print(f"生成的 Arxiv 检索关键词为：{keywords}")
            print(f"生成的 Arxiv 查询表达式为：[{english_topic}]")
            node_warning = ""
        except Exception as e:
            print(f"翻译检索词失败，退回使用原输入: {e}")
            keywords = [user_topic]
            english_topic = user_topic
            node_warning = f"检索词翻译模型调用失败，已退回使用原始输入：{e}"

        return {
            "topic": user_topic,
            "english_topic": english_topic,
            "search_keywords": keywords,
            "next_node": "arxiv_agent",
            "review_retry_count": 0,
            "node_warning": node_warning,
            "node_error": "",
        }

    def build_prompt(self, user_topic: str) -> str:
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        return template.format(user_topic=user_topic)

    def normalize_topic(self, topic: str) -> str:
        return re.sub(r"\s+", " ", str(topic or "")).strip()

    def normalize_keyword(self, keyword: str) -> str:
        keyword = re.sub(r"\s+", " ", str(keyword or "")).strip()
        return keyword.strip("\"'`，,;；")

    def parse_keyword_response(self, raw_text: str) -> tuple[list[str], str]:
        raw_text = str(raw_text or "").strip()
        json_match = re.search(r"\{.*\}", raw_text, re.S)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                keywords = [
                    self.normalize_keyword(keyword)
                    for keyword in data.get("keywords", [])
                    if self.normalize_keyword(keyword)
                ]
                query = self.normalize_keyword(data.get("arxiv_query", ""))
                if keywords:
                    return keywords[:5], query
            except json.JSONDecodeError:
                pass

        candidates = re.split(r"[,;\n，；]+", raw_text)
        keywords = [self.normalize_keyword(item) for item in candidates if self.normalize_keyword(item)]
        return keywords[:5], ""

    def build_arxiv_query(self, keywords: list[str], fallback: str) -> str:
        clean_keywords = [
            self.normalize_keyword(keyword)
            for keyword in keywords
            if self.normalize_keyword(keyword)
        ]
        if not clean_keywords:
            return self.normalize_keyword(fallback)

        quoted_keywords = []
        for keyword in clean_keywords[:5]:
            if " " in keyword:
                quoted_keywords.append(f'"{keyword}"')
            else:
                quoted_keywords.append(keyword)

        if len(quoted_keywords) == 1:
            return quoted_keywords[0]
        return " OR ".join(quoted_keywords)


human_interaction_skill = HumanInteractionSkill()

