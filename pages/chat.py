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
if "chat_processing_status" not in st.session_state:
    st.session_state.chat_processing_status = {
        "is_processing": False,
        "current_message": None,
        "current_image": None,
        "response_started": False
    }

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

# 显示聊天历史
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])
        if "has_image" in message and message["has_image"]:
            st.image(message["image"], caption="用户上传的图片",
                     use_container_width=True)

# 用户输入
user_input = st.chat_input("请输入您的问题...")

# 处理新的用户输入
if user_input and not st.session_state.chat_processing_status["is_processing"]:
    # 设置处理状态
    st.session_state.chat_processing_status = {
        "is_processing": True,
        "current_message": user_input,
        "current_image": uploaded_image,
        "response_started": False
    }

    # 添加用户消息到会话状态
    message_data = {
        "role": "user",
        "content": user_input,
    }
    if uploaded_image:
        message_data["has_image"] = True
        message_data["image"] = uploaded_image
    st.session_state.chat_messages.append(message_data)

# 如果正在处理中
elif st.session_state.chat_processing_status["is_processing"]:
    # 获取当前正在处理的消息
    user_input = st.session_state.chat_processing_status["current_message"]
    uploaded_image = st.session_state.chat_processing_status["current_image"]

    # 如果还没有开始生成响应
    if not st.session_state.chat_processing_status["response_started"]:
        with st.chat_message("assistant", avatar="🤖"):
            with st.status("🤔 正在思考...", expanded=True) as status:
                try:
                    agent = create_chat_agent(st.session_state.current_model)
                    response = get_chat_response(
                        agent, user_input, uploaded_image)
                    st.markdown(response)
                    status.update(label="✅ 回答完成",
                                  state="complete", expanded=True)

                    # 保存响应到会话状态
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": response
                    })

                    # 标记响应已完成
                    st.session_state.chat_processing_status["response_started"] = True

                except Exception as e:
                    error_msg = f"生成回答时出错: {str(e)}"
                    st.error(error_msg)
                    # 保存错误消息到会话状态
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": f"❌ {error_msg}"
                    })
                finally:
                    # 重置处理状态
                    st.session_state.chat_processing_status = {
                        "is_processing": False,
                        "current_message": None,
                        "current_image": None,
                        "response_started": False
                    }

# 添加底部边距
st.markdown("<div style='margin-bottom: 100px'></div>", unsafe_allow_html=True)
