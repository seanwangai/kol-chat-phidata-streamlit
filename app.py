import streamlit as st
from agents import create_agents, get_response, get_expert_names, create_summary_agent, get_summary_response
from pathlib import Path
import requests
import zipfile
import os


def initialize_dropbox():
    """初始化 Dropbox 并下载必要文件"""
    # 获取 URL 参数
    page = st.query_params.get("page", None)

    # 根据页面参数选择不同的 URL 和目标目录
    if page == "kol":
        dropbox_url_key = "DROPBOX_DATA_URL_KOL"
        target_dir = Path("data_kol")
    else:
        dropbox_url_key = "DROPBOX_DATA_URL"
        target_dir = Path("data")

    if dropbox_url_key in st.secrets:
        try:
            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"创建数据目录: {target_dir}")

            # 修改URL为直接下载链接
            url = st.secrets[dropbox_url_key]
            url = url.split('&dl=')[0] + '&dl=1'
            print(f"使用下载链接: {url}")

            # 确保临时文件路径存在
            temp_zip = target_dir / "temp_download.zip"
            print(f"准备下载到: {temp_zip}")

            try:
                # 下载文件
                response = requests.get(url, stream=True)
                response.raise_for_status()

                # 确保文件被完整写入
                with open(temp_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                print(f"下载完成，文件大小: {temp_zip.stat().st_size} bytes")

                # 验证文件
                if not temp_zip.exists():
                    raise FileNotFoundError(f"下载的文件未找到: {temp_zip}")
                if not zipfile.is_zipfile(temp_zip):
                    raise ValueError(f"下载的文件不是有效的ZIP文件: {temp_zip}")

                # 清空目标目录
                print("清理现有文件...")
                for item in target_dir.iterdir():
                    if item != temp_zip:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            import shutil
                            shutil.rmtree(item)

                # 解压文件
                print("开始解压文件...")
                with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
                print("解压完成")

                # 删除临时ZIP文件
                temp_zip.unlink()
                print("已删除临时ZIP文件")

                # 验证解压结果
                expert_count = len(
                    [f for f in target_dir.iterdir() if f.is_dir()])
                print(f"发现 {expert_count} 个专家目录")

                return True

            except Exception as e:
                print(f"处理文件时出错: {str(e)}")
                return False

        except Exception as e:
            print(f"初始化失败: {str(e)}")
            return False

    print(f"警告: 未找到 {dropbox_url_key} 配置信息")
    return False


# 页面配置
st.set_page_config(
    page_title="Investment Titans Chat",
    page_icon="📈",
    layout="wide"
)

# 初始化所有会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_model" not in st.session_state:
    st.session_state.current_model = "gemini-2.0-flash-exp"
if "selected_experts" not in st.session_state:
    st.session_state.selected_experts = []
if "agents" not in st.session_state:
    st.session_state.agents = {}

# 检查数据目录
if 'dropbox_initialized' not in st.session_state:
    page = st.query_params.get("page", None)
    data_dir = Path("data_kol") if page == "kol" else Path("data")

    if data_dir.exists() and any(data_dir.iterdir()):
        print(f"{data_dir} 目录已存在且有内容，跳过下载")
        st.session_state.dropbox_initialized = True
    else:
        st.session_state.dropbox_initialized = initialize_dropbox()

# 如果初始化失败且目录不存在，显示错误信息
if not st.session_state.dropbox_initialized and not (Path("data").exists() or Path("data_kol").exists()):
    st.error("无法初始化专家数据。请确保data目录存在或Dropbox配置正确。")
    st.stop()

# 右侧边栏
with st.sidebar:
    st.header("⚙️ 系统设置")

    # 模型选择
    model_type = st.selectbox(
        "选择模型",
        [
            "gemini-2.0-flash-exp",
            "gemini-exp-1206",
            "gemini-2.0-flash-thinking-exp-1219",
            "deepseek"
        ],
        key="model_type",
        index=list([
            "gemini-2.0-flash-exp",
            "gemini-exp-1206",
            "gemini-2.0-flash-thinking-exp-1219",
            "deepseek"
        ]).index(st.session_state.current_model)
    )

    # 当模型改变时重新创建agents
    if st.session_state.current_model != model_type:
        st.session_state.current_model = model_type
        st.session_state.messages = []
        st.session_state.agents = create_agents(model_type)
        st.session_state.selected_experts = list(
            st.session_state.agents.keys())
        st.rerun()

    # 如果还没有创建agents，现在创建
    if not st.session_state.agents:
        st.session_state.agents = create_agents(model_type)
        st.session_state.selected_experts = list(
            st.session_state.agents.keys())

    # 显示当前可用的专家，并添加选择功能
    st.header("💡 专家列表")

    # 全选/取消全选按钮
    if st.button("全选" if len(st.session_state.selected_experts) < len(st.session_state.agents) else "取消全选"):
        if len(st.session_state.selected_experts) < len(st.session_state.agents):
            st.session_state.selected_experts = list(
                st.session_state.agents.keys())
        else:
            st.session_state.selected_experts = []
        st.rerun()

    # 专家选择
    for agent_name, (_, avatar) in st.session_state.agents.items():
        col1, col2 = st.columns([0.7, 3])
        with col1:
            if st.checkbox(
                label=f"选择{agent_name}",
                value=agent_name in st.session_state.selected_experts,
                key=f"check_{agent_name}",
                label_visibility="collapsed"
            ):
                if agent_name not in st.session_state.selected_experts:
                    st.session_state.selected_experts.append(agent_name)
            else:
                if agent_name in st.session_state.selected_experts:
                    st.session_state.selected_experts.remove(agent_name)
        with col2:
            st.markdown(f"{avatar} {agent_name}")

    # 添加分隔线
    st.markdown("---")

    # 添加更新按钮
    if st.button("🔄 更新专家列表", type="primary"):
        with st.spinner("正在更新专家资料..."):
            if initialize_dropbox():
                # 重新创建agents
                st.session_state.agents = create_agents(
                    st.session_state.current_model)
                st.session_state.selected_experts = list(
                    st.session_state.agents.keys())
                st.success("专家资料更新成功！")
                st.rerun()
            else:
                st.error("更新失败，请检查网络连接或配置。")

# 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agents" not in st.session_state:
    st.session_state.agents = create_agents(model_type)
if "current_response" not in st.session_state:
    st.session_state.current_response = {}
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False
if "error_count" not in st.session_state:
    st.session_state.error_count = 0

# 页面标题
st.title("📈 Investment Titans Chat")

# 在用户输入区域之前添加图片上传
uploaded_image = None
if model_type.startswith("gemini"):
    uploaded_file = st.file_uploader("上传图片（可选）", type=['png', 'jpg', 'jpeg'])
    if uploaded_file is not None:
        # 显示上传的图片
        st.image(uploaded_file, caption="已上传的图片", use_container_width=True)
        uploaded_image = uploaded_file.getvalue()

# 左侧聊天区域
chat_container = st.container()
with chat_container:
    # 显示聊天历史
    for message in st.session_state.messages:
        if message["role"] == "user":
            # 显示用户消息
            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(message["content"])
                if "has_image" in message and message["has_image"]:
                    st.image(message["image"], caption="用户上传的图片",
                             use_container_width=True)
        else:
            # 显示专家回答
            st.markdown(f"### {message.get('agent_name', '专家')}")
            with st.chat_message("assistant", avatar=message.get('avatar', '🤖')):
                st.markdown(message["content"])

# 用户输入
user_input = st.chat_input("请输入您的问题...")

if user_input and not st.session_state.is_processing:
    try:
        # 设置处理状态
        st.session_state.is_processing = True
        st.session_state.error_count = 0

        # 添加用户消息
        message_data = {
            "role": "user",
            "content": user_input,
        }
        if uploaded_image:
            message_data["has_image"] = True
            message_data["image"] = uploaded_image
        st.session_state.messages.append(message_data)

        # 显示用户消息
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input)
            if uploaded_image:
                st.image(uploaded_image, caption="用户上传的图片",
                         use_container_width=True)

        # 存储所有专家的回答
        expert_responses = []

        # 获取选中专家的响应
        for agent_name, (agent, avatar) in st.session_state.agents.items():
            if agent_name in st.session_state.selected_experts:
                with st.status(f"{avatar} {agent_name} 正在思考...", expanded=False) as status:
                    with st.chat_message("assistant", avatar=avatar):
                        try:
                            response = get_response(
                                agent, user_input, uploaded_image)
                            st.markdown(response)
                            status.update(
                                label=f"✅ {agent_name} 已回答", state="complete", expanded=True)

                            response_data = {
                                "role": "assistant",
                                "content": response,
                                "agent_name": agent_name,
                                "avatar": avatar
                            }
                            st.session_state.messages.append(response_data)
                            expert_responses.append(response_data)

                        except Exception as e:
                            error_msg = f"生成回答时出错: {str(e)}"
                            st.error(error_msg)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"❌ {error_msg}",
                                "agent_name": agent_name,
                                "avatar": avatar
                            })
                            st.session_state.error_count += 1

        # 如果有多个专家回答，生成总结
        if len(expert_responses) > 1:
            with st.status("🤔 正在生成总结...", expanded=False) as status:
                try:
                    # 创建总结agent
                    summary_agent = create_summary_agent(
                        st.session_state.current_model)
                    summary = get_summary_response(
                        summary_agent, expert_responses)

                    with st.chat_message("assistant", avatar="🎯"):
                        st.markdown("### 💡 专家观点总结")
                        st.markdown(summary)
                    status.update(label="✨ 总结完成",
                                  state="complete", expanded=True)

                    # 保存总结到消息历史
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": summary,
                        "agent_name": "专家观点总结",
                        "avatar": "🎯"
                    })
                except Exception as e:
                    st.error(f"生成总结时出错: {str(e)}")

    except Exception as e:
        st.error(f"处理请求时出错: {str(e)}")
    finally:
        # 重置处理状态
        st.session_state.is_processing = False

# 添加底部边距
st.markdown("<div style='margin-bottom: 100px'></div>", unsafe_allow_html=True)
