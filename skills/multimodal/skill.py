import base64
import os
from pathlib import Path
from typing import Any

import fitz
import requests
from langchain_core.messages import HumanMessage

from state import ResearchState


PROMPT_TEMPLATE_PATH = Path(__file__).with_name("prompt_template.md")


class MultimodalAnalysisSkill:
    """Extract paper figures from PDFs and summarize them with a vision model."""

    name = "multimodal_figure_analyzer"

    async def arun(self, state: ResearchState, model: Any) -> dict[str, Any]:
        print("\n[MultimodalSkill] 开始精准提取并分析论文架构/实验图表...")
        paper_info = state.get("current_source_paper", {}) or {}
        url = paper_info.get("url")

        if not url:
            print("[MultimodalSkill] 未获取到有效论文链接，跳过多模态分析。")
            return self._skip_result(
                analysis="",
                warning="未获取到有效论文 PDF 链接，已跳过多模态图表分析。",
            )

        try:
            base64_images = self.extract_images_from_url_in_memory(
                url,
                paper_metadata=paper_info,
            )

            if not base64_images:
                print("[MultimodalSkill] 论文中无图表，或链接非 PDF，安全跳过。")
                return self._skip_result(
                    analysis="本篇论文无图表解析内容。",
                    warning="未提取到可分析图表，已跳过多模态图表分析。",
                )

            message = HumanMessage(
                content=self._build_message_content(
                    paper_title=paper_info.get("title", "未知论文"),
                    base64_images=base64_images,
                )
            )

            print(f"[MultimodalSkill] 正在调用视觉模型分析 {len(base64_images)} 张图片...")
            result = await model.ainvoke([message])
            analysis_result = self._normalize_model_content(result.content)

            print("[MultimodalSkill] 图表深度分析完成！")
            return {
                "multimodal_analysis": analysis_result.strip(),
                "next_node": "architect_agent",
                "node_warning": "",
                "node_error": "",
            }

        except Exception as e:
            print(f"[MultimodalSkill] 解析失败: {e}")
            return self._skip_result(
                analysis="",
                warning=f"多模态图表解析失败，已跳过图表分析并继续撰写报告：{e}",
            )

    def resolve_direct_pdf_url(self, raw_url: str, paper_metadata: dict | None = None) -> str:
        """Best-effort conversion from paper pages to direct PDF URLs."""
        if not raw_url:
            return ""

        raw_url = raw_url.strip()

        if "arxiv.org/abs/" in raw_url:
            return raw_url.replace("/abs/", "/pdf/") + ".pdf"

        if paper_metadata and paper_metadata.get("arxivId"):
            return f"https://arxiv.org/pdf/{paper_metadata['arxivId']}.pdf"

        if "semanticscholar.org/paper/" in raw_url:
            paper_id = raw_url.split("/")[-1]
            try:
                s2_api = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=openAccessPdf,externalIds"
                resp = requests.get(s2_api, timeout=5).json()

                if resp.get("externalIds", {}).get("ArXiv"):
                    return f"https://arxiv.org/pdf/{resp['externalIds']['ArXiv']}.pdf"

                if resp.get("openAccessPdf") and resp.get("openAccessPdf").get("url"):
                    return resp["openAccessPdf"]["url"]
            except Exception as e:
                print(f"[MultimodalSkill] Semantic Scholar PDF 解析失败: {e}")

        if "dl.acm.org/doi/pdf/" in raw_url:
            return raw_url

        if raw_url.lower().endswith(".pdf"):
            return raw_url

        return raw_url

    def extract_images_from_url_in_memory(
        self,
        url: str,
        paper_metadata: dict | None = None,
        max_images: int = 4,
    ) -> list[str]:
        """Resolve a PDF URL, download it, and extract useful embedded images."""
        pdf_url = self.resolve_direct_pdf_url(url, paper_metadata)

        if not self._looks_like_pdf_url(pdf_url):
            print(f"[MultimodalSkill] 无法解析出直接可下载的 PDF 链接，已安全跳过: {url}")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/pdf",
        }

        try:
            print("[MultimodalSkill] 准备下载 PDF...")
            response = requests.get(pdf_url, headers=headers, timeout=20)
            response.raise_for_status()
            pdf_bytes = response.content

            if not pdf_bytes.startswith(b"%PDF"):
                print("[MultimodalSkill] 下载到的内容不是合法 PDF，可能是反爬虫验证页。")
                return []

        except Exception as e:
            print(f"[MultimodalSkill] PDF 下载失败: {e}")
            return []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            return self._extract_base64_images(doc, max_images=max_images)
        except Exception as e:
            print(f"[MultimodalSkill] PDF 解析过程出错: {e}")
            return []

    def guess_image_mime_from_base64(self, base64_data: str) -> str:
        try:
            header = base64.b64decode(base64_data[:32], validate=False)
        except Exception:
            return "jpeg"

        if header.startswith(b"\x89PNG"):
            return "png"
        if header.startswith(b"\xff\xd8"):
            return "jpeg"
        if header.startswith(b"GIF"):
            return "gif"
        if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
            return "webp"
        return "jpeg"

    def _build_message_content(self, paper_title: str, base64_images: list[str]) -> list[dict[str, str]]:
        content_list = [
            {
                "type": "text",
                "text": self._analysis_prompt(paper_title),
            }
        ]

        for b64_img in base64_images:
            content_list.append(
                {
                    "type": "image",
                    "image": self._image_to_message_url(b64_img),
                }
            )

        return content_list

    def _analysis_prompt(self, paper_title: str) -> str:
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        return template.format(paper_title=paper_title)

    def _image_to_message_url(self, image_ref: str) -> str:
        if image_ref.startswith("http") or image_ref.startswith("data:image/"):
            return image_ref

        if os.path.exists(image_ref):
            with open(image_ref, "rb") as image_file:
                base64_data = base64.b64encode(image_file.read()).decode("utf-8")

            ext = image_ref.split(".")[-1].lower()
            mime_type = "jpeg" if ext in ["jpg", "jpeg"] else ("png" if ext == "png" else "jpeg")
            return f"data:image/{mime_type};base64,{base64_data}"

        mime_type = self.guess_image_mime_from_base64(image_ref)
        return f"data:image/{mime_type};base64,{image_ref}"

    def _extract_base64_images(self, doc: fitz.Document, max_images: int) -> list[str]:
        base64_images = []
        try:
            for page_num in range(min(len(doc), 15)):
                page = doc.load_page(page_num)
                image_list = page.get_images(full=True)

                for img_info in image_list:
                    xref = img_info[0]
                    width = img_info[2]
                    height = img_info[3]

                    if not self._is_candidate_figure(width, height):
                        continue

                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    if len(image_bytes) <= 30720:
                        continue

                    base64_images.append(base64.b64encode(image_bytes).decode("utf-8"))
                    if len(base64_images) >= max_images:
                        return base64_images

            return base64_images
        finally:
            doc.close()

    def _is_candidate_figure(self, width: int, height: int) -> bool:
        if width <= 400 or height <= 250:
            return False

        ratio = width / height
        return 0.3 < ratio < 3.5

    def _looks_like_pdf_url(self, pdf_url: str) -> bool:
        if not pdf_url:
            return False
        return (
            pdf_url.lower().endswith(".pdf")
            or "dl.acm.org" in pdf_url
            or "arxiv.org" in pdf_url
        )

    def _normalize_model_content(self, raw_content: Any) -> str:
        if isinstance(raw_content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_content
            )
        return str(raw_content or "")

    def _skip_result(self, analysis: str, warning: str) -> dict[str, str]:
        return {
            "multimodal_analysis": analysis,
            "next_node": "architect_agent",
            "node_warning": warning,
            "node_error": "",
        }


multimodal_analysis_skill = MultimodalAnalysisSkill()

