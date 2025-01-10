import streamlit as st
from phi.model.google import GeminiOpenAIChat
from phi.model.deepseek import DeepSeekChat
from phi.agent import Agent
from itertools import cycle

# 定义可用的模型
MODELS = {
    "gemini-2.0-flash-thinking-exp-1219": "Gemini Flash Thinking",
    "gemini-2.0-flash-exp": "Gemini Flash",
    "gemini-exp-1206": "Gemini 1206",
    "deepseek": "DeepSeek"
}

# 页面配置
st.set_page_config(
    page_title="AI Chat",
    page_icon="💭",
    layout="wide"
)

# 初始化会话状态
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_is_processing" not in st.session_state:
    st.session_state.chat_is_processing = False
if "chat_error_count" not in st.session_state:
    st.session_state.chat_error_count = 0
if "current_model" not in st.session_state:
    st.session_state.current_model = "gemini-2.0-flash-thinking-exp-1219"

# API key 轮换


def get_next_api_key():
    if "api_key_cycle" not in st.session_state:
        st.session_state.api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
    return next(st.session_state.api_key_cycle)

# 创建agent


def create_chat_agent(model_type: str):
    if model_type.startswith("gemini"):
        model = GeminiOpenAIChat(
            id=model_type,
            api_key=get_next_api_key(),
        )
    elif model_type == "deepseek":
        model = DeepSeekChat(
            api_key=st.secrets["DEEPSEEK_API_KEY"],
        )
    else:
        raise ValueError(f"不支持的模型类型: {model_type}")

    return Agent(
        model=model,
        system_prompt="你是一个专业的AI助手，请用专业、准确、友善的方式回答问题。",
        markdown=True
    )

# 获取响应


def get_chat_response(agent: Agent, message: str, image=None, max_retries: int = 3) -> str:
    for attempt in range(max_retries + 1):
        try:
            # 更新API key（仅对Gemini模型）
            if isinstance(agent.model, GeminiOpenAIChat):
                agent.model.api_key = get_next_api_key()
                print(f"使用 API Key: {agent.model.api_key[:10]}...")

            if image and isinstance(agent.model, GeminiOpenAIChat):
                response = agent.run(message, images=[image])
            else:
                response = agent.run(message)
            return response.content

        except Exception as e:
            error_str = str(e)
            print(f"第 {attempt + 1} 次尝试失败: {error_str}")

            if "429" in error_str and "RESOURCE_EXHAUSTED" in error_str:
                print("检测到配额超限错误，正在切换到新的 API Key...")
                if attempt < max_retries:
                    continue

            if attempt < max_retries:
                print("正在重试...")
                continue
            else:
                print("已达到最大重试次数")
                return f"抱歉，我现在遇到了技术问题（{error_str}）。请稍后再试。"


# 侧边栏
with st.sidebar:
    st.header("⚙️ 设置")

    # 模型选择
    selected_model = st.selectbox(
        "选择模型",
        list(MODELS.keys()),
        format_func=lambda x: MODELS[x],
        index=list(MODELS.keys()).index(st.session_state.current_model)
    )

    # 如果模型改变，更新会话状态
    if selected_model != st.session_state.current_model:
        st.session_state.current_model = selected_model
        st.session_state.chat_messages = []  # 清空对话历史
        st.rerun()

    # 清空对话
    if st.button("🗑️ 清空对话历史", type="primary"):
        st.session_state.chat_messages = []
        st.rerun()

    # 系统状态
    st.markdown("---")
    st.markdown("### 📊 系统状态")
    st.info(f"""
    - 模型: {MODELS[st.session_state.current_model]}
    - 消息数: {len(st.session_state.chat_messages)}
    - 状态: {'🟢 正常' if not st.session_state.chat_error_count else '🔴 异常'}
    """)

# 页面标题
st.title("💭 AI Chat")

# 图片上传（仅对Gemini模型显示）
uploaded_image = None
if st.session_state.current_model.startswith("gemini"):
    uploaded_file = st.file_uploader("上传图片（可选）", type=['png', 'jpg', 'jpeg'])
    if uploaded_file is not None:
        st.image(uploaded_file, caption="已上传的图片", use_container_width=True)
        uploaded_image = uploaded_file.getvalue()

# 聊天区域
chat_container = st.container()
with chat_container:
    # 显示聊天历史
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🤖"):
            st.markdown(message["content"])
            if "has_image" in message and message["has_image"]:
                st.image(message["image"], caption="用户上传的图片",
                         use_container_width=True)

# 用户输入
user_input = st.chat_input("请输入您的问题...")

if user_input and not st.session_state.chat_is_processing:
    try:
        # 设置处理状态
        st.session_state.chat_is_processing = True
        st.session_state.chat_error_count = 0

        # 添加用户消息
        message_data = {
            "role": "user",
            "content": user_input,
        }
        if uploaded_image:
            message_data["has_image"] = True
            message_data["image"] = uploaded_image
        st.session_state.chat_messages.append(message_data)

        # 显示用户消息
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input)
            if uploaded_image:
                st.image(uploaded_image, caption="用户上传的图片",
                         use_container_width=True)

        # 获取AI响应
        with st.chat_message("assistant", avatar="🤖"):
            with st.status("🤔 正在思考...", expanded=True):
                try:
                    agent = create_chat_agent(st.session_state.current_model)
                    response = get_chat_response(
                        agent, user_input, uploaded_image)
                    st.markdown(response)

                    # 保存响应
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response
                    })

                except Exception as e:
                    st.error(f"生成回答时出错: {str(e)}")

    except Exception as e:
        st.error(f"处理请求时出错: {str(e)}")
    finally:
        # 重置处理状态
        st.session_state.chat_is_processing = False
