from state import ResearchState
from config import architect_model
from skills.architect import architect_skill

model = architect_model


async def architect_agent_node(state: ResearchState):
    print("\n[Architect] 节点启动...")
    return await architect_skill.arun(state, model)


if __name__ == "__main__":
    test = model.invoke("你是什么模型？")
    print(test.content)
    # i = None
    # print(not i)
