from phi.model.google import GeminiOpenAIChat
from phi.model.deepseek import DeepSeekChat
from phi.agent import Agent
from typing import Dict
import streamlit as st
from pathlib import Path
from utils import get_expert_content
import random
from itertools import cycle


# 定义可用的头像列表
AVATARS = ["🤓", "🧙‍♂️", "👨‍🔬", "👩‍🔬", "👨‍💻", "👩‍💻",
           "🦹‍♂️", "🦸‍♀️", "🧝‍♂️", "🧝‍♀️", "🧚‍♂️", "🧚‍♀️"]

GEMINI_MODELS = {
    "gemini-exp-1206": "gemini-exp-1206",
    "gemini-2.0-flash-thinking-exp-1219": "gemini-2.0-flash-thinking-exp-1219",
    "gemini-2.0-flash-exp": "gemini-2.0-flash-exp"
}

# 创建一个API key循环器
api_key_cycle = None


def get_next_api_key():
    """获取下一个API key"""
    global api_key_cycle
    if api_key_cycle is None:
        api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
    return next(api_key_cycle)


def create_model(model_type: str):
    """创建指定类型的模型"""
    if model_type.startswith("gemini"):
        return GeminiOpenAIChat(
            id=GEMINI_MODELS.get(model_type, "gemini-exp-1206"),
            api_key=get_next_api_key(),  # 使用循环的API key
        )
    elif model_type == "deepseek":
        return DeepSeekChat(
            api_key=st.secrets["DEEPSEEK_API_KEY"],
        )
    else:
        raise ValueError(f"不支持的模型类型: {model_type}")


def create_agent(expert_folder: Path, model_type: str, lazy_loading: bool = False, custom_prompt_ending: str = None) -> Agent:
    """根据专家文件夹创建Agent

    Args:
        expert_folder: 专家文件夹路径
        model_type: 模型类型
        lazy_loading: 是否使用延迟加载模式，默认为False
        custom_prompt_ending: 自定义提示词结尾，默认为None
    """
    # 获取专家名称（文件夹名）
    expert_name = expert_folder.name

    # 如果使用延迟加载模式，创建一个轻量级的Agent占位符
    if lazy_loading:
        # 创建一个简单的系统提示词，不加载专家内容
        system_prompt = f"你是专家 {expert_name}，等待用户提问后将加载完整知识库。"

        # 创建并返回轻量级agent
        return Agent(
            model=create_model(model_type),
            system_prompt=system_prompt,
            markdown=True
        )
    else:
        # 正常模式：读取专家资料
        expert_content = get_expert_content(expert_folder)
        print('正常模式：读取专家资料')
        print(expert_content[4000:4100])
        print('====in agent custom_prompt_ending==')
        print(custom_prompt_ending)

        # 使用传入的 custom_prompt_ending，如果为 None 则使用默认值
        if custom_prompt_ending and custom_prompt_ending.strip():
            prompt_ending = custom_prompt_ending
            print(f"使用传入的自定义提示词: {prompt_ending}")
        else:
            # 从 session_state 获取
            prompt_ending = st.session_state.get('custom_prompt_ending')
            print(f"从 session_state 获取的提示词: {prompt_ending}")

            # 如果仍然为 None 或空字符串，使用默认值
            if not prompt_ending or not prompt_ending.strip():
                page = st.query_params.get("page", None)
                if page == "kol":
                    prompt_ending = "學習此寫作風格，根据我輸入的主題，開始寫作："
                else:
                    prompt_ending = f"""以上是 {expert_name} 的知識。

You are now embodying {expert_name}, a legendary investor and finance expert. You are known for your rigorous critical thinking, deep knowledge in finance, valuation and strategic decision-making.

Your primary mission is to act as an investment mentor and analyst, guiding professional investors and analysts in sharpening their thinking and investment theses.

When a user presents an investment pitch, your structured response should always follow this format:

---

### Step 0: Initial Rating  
Start your answer by choosing one of the following and explain **why**:  
📉📉 Strong Short / 📉 Short / ⚖️ Neutral / 📈 Long / 📈📈 Strong Long  
盡量不選⚖️ Neutral，除非真的是然要選⚖️ Neutral

**Begin your response with this sentence:**  
#### {{📉📉 Strong Short / 📈📈 Strong Long  ...}} 
身為 {expert_name}，我認為這是... ，因為..

---
### 🧭 Step 1: Investment Philosophy
嚴格使用 {expert_name} 的知識，{expert_name} 知識中提到的所有投資邏輯，深度去評估提到的這間公司
列出我所有提到投資邏輯，逐一去解析是否有達標


### 🧠 Step 2: Core Investment Logic  
Explain your logic based on your investing framework:
- Is the thesis internally consistent?
- Are key drivers realistic?
- Are there critical blind spots?

Use bullet points and back your views with examples or financial reasoning **based on your knowledge**.

---

### 🔍 Step 3: Challenge & Deepen  
Ask **probing questions** to test the pitch:
- What assumptions need more clarity?
- Are valuation inputs reasonable?
- What sensitivity or scenario analyses are missing?

Challenge them like a top-tier investment committee would.

---

### 📚 Step 4: Educational Insight  
Provide **1-2 educational insights** that help the user level up:
- Point out flaws in logic or modeling
- Suggest better frameworks or comparables
- Reference valuation theory or real-world cases

---

### ⚖️ Step 5: Bias & Objectivity Check  
Ask the user to examine potential **biases**:
- Confirmation bias?
- Overconfidence in management?
- Narrative vs. numbers?

---

## Language & Tone Guidelines:
- 使用中文回答，除非有特別指定
- Tone: incisive, Socratic, yet educational
- Do not fabricate facts—use only the embedded knowledge of {expert_name}

"""

                print(f"使用默认提示词: {prompt_ending}")

        # 创建系统提示词
        system_prompt = f""" 你是专家 {expert_name} ，以下是你寫過的書，以此書內容作為你的投資邏輯框架，回答都要由你的投資邏輯為基礎回答：
{expert_content}

{prompt_ending}"""
        print('============')
        print('最终使用的提示词结尾:')
        print(prompt_ending)

        # 创建并返回完整agent
        return Agent(
            model=create_model(model_type),
            system_prompt=system_prompt,
            markdown=True
        )


def get_response(agent_info, message: str, image=None, pdf_content=None, max_retries: int = 3, custom_prompt_ending: str = None) -> str:
    """获取 Agent 的响应，支持图片和PDF输入

    Args:
        agent_info: 可以是Agent对象或者(agent, avatar, expert_folder)元组
        message: 用户消息
        image: 可选的图片
        pdf_content: 可选的PDF内容
        max_retries: 最大重试次数
        custom_prompt_ending: 自定义提示词结尾
    """
    print('=======')
    print(agent_info)
    print(isinstance(agent_info, tuple))
    print('custom_prompt_ending:', custom_prompt_ending)  # 添加日志
    print('=======')

    # 检查agent_info是否是Agent对象
    from phi.agent import Agent
    if isinstance(agent_info, Agent):
        # 如果是Agent对象，直接使用
        print("使用旧版本调用方式 - 直接传入Agent对象")
        agent = agent_info
    elif isinstance(agent_info, tuple) and len(agent_info) == 3:
        # 如果是元组，解构元组
        print('in the isinstance(agent_info, tuple) and len(agent_info) == 3')
        agent, avatar, expert_folder = agent_info
        print(agent.system_prompt)
        # 检查是否是轻量级agent（通过检查系统提示词是否包含完整知识库）
        if "等待用户提问后将加载完整知识库" in agent.system_prompt:
            print(f"首次使用专家 {expert_folder.name}，正在加载完整知识库...")
            # 创建完整的agent替换轻量级agent
            agent = create_agent(
                expert_folder,
                agent.model.id.split('/')[-1],
                lazy_loading=False,
                custom_prompt_ending=custom_prompt_ending  # 使用传入的值
            )
            # 更新元组中的agent引用
            agent_info = (agent, avatar, expert_folder)
    else:
        # 其他情况，假设agent_info就是agent
        print("使用旧版本调用方式 - 未知类型")
        agent = agent_info

    # 如果有PDF内容，将其添加到消息中
    if pdf_content:
        # 截取PDF内容的前2000个字符，避免提示词过长
        truncated_pdf = pdf_content[:2000] + \
            "..." if len(pdf_content) > 2000 else pdf_content
        message += f"\n\n以下是PDF文档内容：\n{truncated_pdf}\n\n请分析这份PDF文档并将其纳入你的回答。"

    for attempt in range(max_retries + 1):
        try:
            # 在每次请求前更新agent的API key
            if isinstance(agent.model, GeminiOpenAIChat):
                agent.model.api_key = get_next_api_key()
                # 只打印前10个字符
                print(f"使用 API Key: {agent.model.api_key[:10]}...")
                if image:
                    # 如果有图片，使用 vision 方法
                    response = agent.run(message, images=[image])
                else:
                    response = agent.run(message)
            else:
                response = agent.run(message)
            return response.content
        except Exception as e:
            error_str = str(e)
            print(f"第 {attempt + 1} 次尝试失败: {error_str}")

            # 检查是否是配额超限错误
            if "429" in error_str and "RESOURCE_EXHAUSTED" in error_str:
                print("检测到配额超限错误，正在切换到新的 API Key...")
                if attempt < max_retries:
                    continue

            # 其他错误或已达到最大重试次数
            if attempt < max_retries:
                print("正在重试...")
                continue
            else:
                print("已达到最大重试次数")
                return f"抱歉，我现在遇到了技术问题（{error_str}）。请稍后再试。"


def create_agents(model_type: str = "gemini-2.0-flash-exp", lazy_loading: bool = True, custom_prompt_ending: str = None) -> Dict[str, tuple]:
    """根据目录创建agents，并为每个专家分配头像

    Args:
        model_type: 模型类型
        lazy_loading: 是否使用延迟加载模式，默认为True
        custom_prompt_ending: 自定义提示词结尾，默认为None
    """
    print("\n开始创建专家系统...")
    print('== in create_agents - custom_prompt_ending ==')
    print(custom_prompt_ending)

    agents = {}
    # 根据页面参数选择目录
    page = st.query_params.get("page", None)
    data_dir = Path("data_kol") if page == "kol" else Path("data")

    used_avatars = set()

    if not data_dir.exists():
        print(f"警告: {data_dir} 目录不存在")
        return agents

    # 获取并排序文件夹列表
    expert_folders = sorted(list(data_dir.iterdir()))

    for expert_folder in expert_folders:
        if expert_folder.is_dir():
            try:
                print('==============')
                print('# 使用延迟加载模式创建agent')
                agent = create_agent(
                    expert_folder, model_type, lazy_loading, custom_prompt_ending)
                available_avatars = list(set(AVATARS) - used_avatars)
                if not available_avatars:
                    available_avatars = AVATARS
                avatar = random.choice(available_avatars)
                used_avatars.add(avatar)

                agents[expert_folder.name] = (agent, avatar, expert_folder)
                print(
                    f"✅ 成功创建专家: {expert_folder.name} ({avatar}) {'[延迟加载]' if lazy_loading else ''}")
            except Exception as e:
                print(f"❌ 创建专家 {expert_folder.name} 失败: {str(e)}")

    print(f"\n共创建 {len(agents)} 个专家")
    print("专家创建完成\n")
    return agents


def get_expert_names() -> list:
    """获取所有专家名称"""
    page = st.query_params.get("page", None)
    data_dir = Path("data_kol") if page == "kol" else Path("data")
    return [folder.name for folder in data_dir.iterdir() if folder.is_dir()]


def create_summary_agent(model_type: str) -> Agent:
    """创建总结 Agent"""
    system_prompt = """你是一个总结专家，你的任务是：
1. 分析和总结其他专家的回答
2. 提取每个专家观点的核心内容
3. 找出专家们观点的共同点和差异点
4. 给出一个全面的总结

请以下面的格式输出：
📝 核心观点总结：
[总结各个专家的核心观点]

🔍 共同点：
[列出专家们观点的共同之处]

💭 差异点：
[列出专家们观点的主要差异]

🎯 综合建议：
[基于所有专家意见给出的综合建议]
"""
    return Agent(
        model=create_model(model_type),
        system_prompt=system_prompt,
        markdown=True
    )


def get_summary_response(summary_agent: Agent, expert_responses: list) -> str:
    """获取总结 Agent 的响应"""
    # 构建输入信息
    summary_input = "请总结以下专家的回答：\n\n"
    for response in expert_responses:
        summary_input += f"【{response['agent_name']
                             }】的观点：\n{response['content']}\n\n"

    # 获取总结
    try:
        response = summary_agent.run(summary_input)
        return response.content
    except Exception as e:
        print(f"生成总结失败: {str(e)}")
        return "抱歉，生成总结时遇到了问题。"
