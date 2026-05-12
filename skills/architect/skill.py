from pathlib import Path
from textwrap import dedent
from typing import Any

from langchain_core.messages import HumanMessage

from memory.paper_knowledge import retrieve_related_paper_knowledge, save_paper_knowledge
from state import ResearchState
from utils import extract_github_links_as_markdown


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompt_template.md")


class ArchitectSkill:
    """Build and run the Chief Architect report-writing capability."""

    name = "architect_report_writer"

    async def arun(self, state: ResearchState, model: Any) -> dict[str, Any]:
        existing_report = state.get("final_report", "")
        is_revision = state.get("is_exit") is False
        final_prompt, papers_list = await self.build_prompt(state)

        try:
            response = await model.ainvoke([HumanMessage(content=final_prompt)])
            print("[ArchitectSkill] 研究报告撰写/修改完成。")
            report_content = response.content
            node_error = ""
        except Exception as e:
            print(f"[ArchitectSkill] 报错：大模型调用失败 - {e}")
            report_content = existing_report
            node_error = f"Architect 报告生成模型调用失败：{e}"

        result = {
            "final_report": report_content,
            "next_node": "FINISH" if node_error and not report_content else "reviewer_agent",
            "node_error": node_error,
            "node_warning": "",
        }

        if report_content and not node_error:
            knowledge_warning = await self._save_paper_knowledge(state, report_content)
            if knowledge_warning:
                result["node_warning"] = knowledge_warning

        if not is_revision:
            github_section = extract_github_links_as_markdown(papers_list)
            if github_section:
                print("[ArchitectSkill] 已成功提取 GitHub 链接，暂存至 State 中。")

            result.update(
                {
                    "is_exit": False,
                    "GitHub_link_section": github_section,
                }
            )

        return result

    async def build_prompt(self, state: ResearchState) -> tuple[str, list[str]]:
        topic = state.get("topic", "未知主题")
        current_paper = state.get("current_source_paper", {}) or {}
        paper_title = current_paper.get("title", "未知论文")
        feedback_data = state.get("review_feedback", "")
        latest_feedback, historical_feedbacks = self._split_feedback(feedback_data)

        papers_list = state.get("arxiv_papers", [])
        web_list = state.get("web_search_results", [])
        papers_content = self._stringify_content(papers_list)
        web_content = self._stringify_content(web_list)
        multimodal_analysis = state.get("multimodal_analysis", "")
        paper_meta_text = self._paper_meta_text(current_paper)

        lessons_text = await self._retrieve_lessons(topic)
        knowledge_query = f"{topic} {paper_title}"
        paper_knowledge_text = await self._retrieve_paper_knowledge(knowledge_query)

        if state.get("is_exit") is False:
            print("[ArchitectSkill] 收到修改意见，进入【报告大修】模式...")
            prompt_context = self._revision_context(
                latest_feedback=latest_feedback,
                historical_feedbacks=historical_feedbacks,
                existing_report=state.get("final_report", ""),
                paper_meta_text=paper_meta_text,
                papers_content=papers_content,
                multimodal_analysis=multimodal_analysis,
                web_content=web_content,
                lessons_text=lessons_text,
                paper_knowledge_text=paper_knowledge_text,
            )
        else:
            print("[ArchitectSkill] 资料收集完毕，进入【初稿撰写】模式...")
            prompt_context = self._draft_context(
                paper_meta_text=paper_meta_text,
                papers_content=papers_content,
                multimodal_analysis=multimodal_analysis,
                web_content=web_content,
                lessons_text=lessons_text,
                paper_knowledge_text=paper_knowledge_text,
            )

        shared_instructions = self._shared_instructions(
            topic=topic,
            paper_title=paper_title,
        )

        return f"{prompt_context}\n\n{shared_instructions}", papers_list

    def _shared_instructions(self, topic: str, paper_title: str) -> str:
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        return template.format(topic=topic, paper_title=paper_title)

    async def _retrieve_lessons(self, topic: str) -> str:
        try:
            from memory.lessons import retrieve_past_lessons

            lessons = await retrieve_past_lessons(topic)
        except Exception as e:
            print(f"[ArchitectSkill] 历史经验检索失败，已降级为空经验：{e}")
            return "无明显历史经验。"

        return lessons if lessons else "无明显历史经验。"

    async def _retrieve_paper_knowledge(self, query: str) -> str:
        return await retrieve_related_paper_knowledge(query, top_k=3)

    async def _save_paper_knowledge(self, state: ResearchState, report: str) -> str:
        try:
            message = await save_paper_knowledge(state, report)
            print(f"[ArchitectSkill] {message}")
            return ""
        except Exception as e:
            warning = f"论文知识库写入失败，报告流程已继续：{e}"
            print(f"[ArchitectSkill] {warning}")
            return warning

    def _revision_context(
        self,
        *,
        latest_feedback: str,
        historical_feedbacks: list[str],
        existing_report: str,
        paper_meta_text: str,
        papers_content: str,
        multimodal_analysis: str,
        web_content: str,
        lessons_text: str,
        paper_knowledge_text: str,
    ) -> str:
        historical_text = historical_feedbacks if historical_feedbacks else "无"
        return dedent(
            f"""
            =========================================
            【输入数据】
            <主管最新修改意见>
            {latest_feedback}
            </主管最新修改意见>

            <历史修改意见参考>
            {historical_text}
            </历史修改意见参考>

            <当前待修改的初稿>
            {existing_report}
            </当前待修改的初稿>

            <当前论文元信息>
            {paper_meta_text}
            </当前论文元信息>

            <原始真实研究资料> (⚠️大修时请务必对照原始资料，严禁凭空捏造！)
            {papers_content}
            </原始真实研究资料>

            <论文图表解析>
            {multimodal_analysis}
            </论文图表解析>

            <网页补充信息>
            {web_content}
            </网页补充信息>

            <历史踩坑经验>
            {lessons_text}
            </历史踩坑经验>

            <相关论文知识库>
            {paper_knowledge_text}
            </相关论文知识库>
            =========================================
            """
        ).strip()

    def _draft_context(
        self,
        *,
        paper_meta_text: str,
        papers_content: str,
        multimodal_analysis: str,
        web_content: str,
        lessons_text: str,
        paper_knowledge_text: str,
    ) -> str:
        return dedent(
            f"""
            =========================================
            【输入数据】
            <当前论文元信息>
            {paper_meta_text}
            </当前论文元信息>

            <原始真实研究资料>
            {papers_content}
            </原始真实研究资料>

            <论文图表解析>
            {multimodal_analysis}
            </论文图表解析>

            <网页补充信息>
            {web_content}
            </网页补充信息>

            <历史踩坑经验>
            {lessons_text}
            </历史踩坑经验>

            <相关论文知识库>
            {paper_knowledge_text}
            </相关论文知识库>
            =========================================
            """
        ).strip()

    def _split_feedback(self, feedback_data: Any) -> tuple[str, list[str]]:
        if isinstance(feedback_data, list):
            latest_feedback = feedback_data[-1] if feedback_data else ""
            historical_feedbacks = feedback_data[:-1] if len(feedback_data) > 1 else []
            return latest_feedback, historical_feedbacks

        return str(feedback_data), []

    def _paper_meta_text(self, current_paper: dict[str, Any]) -> str:
        return "\n".join(
            f"{key}: {value}" for key, value in current_paper.items() if value
        ) or "无"

    def _stringify_content(self, value: Any) -> str:
        if isinstance(value, list):
            return "\n\n".join(str(item) for item in value)
        return str(value or "")


architect_skill = ArchitectSkill()
