from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompt_template.md")


class PaperScreeningSkill:
    """Decide whether a crawled Arxiv paper is worth downstream reading."""

    name = "arxiv_paper_screening"

    async def arun(
        self,
        *,
        user_topic: str,
        search_query: str,
        title: str,
        abstract: str,
        categories: list[str],
        model: Any,
    ) -> tuple[bool, str, str]:
        prompt = self.build_prompt(
            user_topic=user_topic,
            search_query=search_query,
            title=title,
            abstract=abstract,
            categories=categories,
        )

        try:
            response = await model.ainvoke([HumanMessage(content=prompt)])
            decision_text = str(response.content or "").strip()
        except Exception as e:
            warning = f"论文初筛模型调用失败，已保守放行当前候选论文：{e}"
            print(f"[PaperScreeningSkill] {warning}")
            return True, warning, warning

        return self.parse_decision(decision_text)

    def build_prompt(
        self,
        *,
        user_topic: str,
        search_query: str,
        title: str,
        abstract: str,
        categories: list[str],
    ) -> str:
        category_text = ", ".join(categories) if categories else "Arxiv 未提供"
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        return template.format(
            user_topic=user_topic,
            search_query=search_query,
            title=title,
            category_text=category_text,
            abstract=abstract or "Arxiv 未提供摘要",
        ).strip()

    def parse_decision(self, decision_text: str) -> tuple[bool, str, str]:
        if "[SKIP]" in decision_text:
            return False, decision_text, ""
        if "[READ]" in decision_text:
            return True, decision_text, ""

        warning = f"论文初筛模型输出格式异常，已保守放行。原始输出：{decision_text[:120]}"
        print(f"[PaperScreeningSkill] {warning}")
        return True, decision_text, warning


paper_screening_skill = PaperScreeningSkill()

