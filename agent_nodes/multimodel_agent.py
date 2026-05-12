from state import ResearchState
from config import vision_model
from skills.multimodal import multimodal_analysis_skill


async def multimodal_agent_node(state: ResearchState):
    return await multimodal_analysis_skill.arun(state, vision_model)

