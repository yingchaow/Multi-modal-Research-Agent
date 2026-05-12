Multi-modal Research Agent (LangGraph Edition)

这是一个基于 **LangGraph** 构建的多智能体学术研究系统。它能够自动检索顶级会议论文（Semantic Scholar），利用 **Qwen-VL-Max** 进行多模态图表解析，并通过人类主管（Human-in-the-loop）的实时干预来生成高质量、数千字的学术研究报告。

## 核心特性

- **多智能体协同架构**：采用分布式专家模型，包含 `Arxiv Agent`（检索）、`Architect Agent`（架构/撰写）、`Multimodal Agent`（视觉解析）、`Reviewer Agent`（评审）。
- **人类决策闭环 (Human-in-the-loop)**：在生成提纲阶段引入“人类主管”节点，支持批准、打回重写或更换论文等 4 种交互决策。
- **状态持久化 (Redis Persistence)**：基于 Redis 实现了工业级的会话恢复机制（Thread ID），支持断线重连与历史会话唤醒。
- **多模态深度解析**：使用“PDF嗅探器”，突破学术网站反爬限制，调用多模态模型对论文架构图与实验图表进行深度语义分析。
- **全栈流式交互**：后端采用 FastAPI + SSE 实现打字机效果，前端通过 Tailwind CSS 构建现代化的响应式控制台。

## 系统架构

本项目采用图拓扑结构进行逻辑流转：
1. **启动**：用户输入主题。
2. **检索**：Agent 获取相关顶会论文及元数据。
3. **解析**：Multimodal Agent 下载 PDF 并提取核心实验图表。
4. **初稿**：Architect Agent 结合图表解析结果撰写详细提纲。
5. **挂起**：系统自动进入暂停状态，等待 Web 端人类用户的决策。
6. **循环/终结**：根据人类反馈，系统会退回检索阶段、重写报告或生成最终 Markdown/PDF 文档。

## 快速开始

### 环境配置
推荐在 macOS (M1/M2) 的虚拟环境下运行：

```bash
# 创建并激活环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

### 环境变量

复制示例文件并填写自己的密钥：

```bash
cp .env.example .env
```
