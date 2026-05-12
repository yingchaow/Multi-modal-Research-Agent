from state import ResearchState
from config import human_interaction_model
from skills.human_interaction import human_interaction_skill


async def human_interaction_agent_node(state: ResearchState):
    return await human_interaction_skill.arun(state, human_interaction_model)


if __name__ == "__main__":
    test = human_interaction_model.invoke("你是什么模型？")
    print(test.content)

