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

    # 根据页面参数选择不同的 URL
    dropbox_url_key = "DROPBOX_DATA_URL_KOL" if page == "kol" else "DROPBOX_DATA_URL"

    if dropbox_url_key in st.secrets:
        try:
            # 创建 data 目录
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            print(f"创建数据目录: {data_dir}")

            # 修改URL为直接下载链接
            url = st.secrets[dropbox_url_key]
            # 移除现有的 dl 参数
            url = url.split('&dl=')[0]
            # 添加新的 dl 参数
            url += '&dl=1'
            print(f"使用下载链接: {url}")

            # 确保临时文件路径存在
            temp_zip = data_dir / "temp_download.zip"
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

                # 验证文件是否存在和是否为有效的zip文件
                if not temp_zip.exists():
                    raise FileNotFoundError(f"下载的文件未找到: {temp_zip}")

                if not zipfile.is_zipfile(temp_zip):
                    raise ValueError(f"下载的文件不是有效的ZIP文件: {temp_zip}")

                # 清空 data 目录
                print("清理现有文件...")
                for item in data_dir.iterdir():
                    if item != temp_zip:  # 保留刚下载的zip文件
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            import shutil
                            shutil.rmtree(item)

                # 解压文件
                print("开始解压文件...")
                with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                    # 显示zip文件内容
                    print("ZIP文件内容:")
                    for file_info in zip_ref.filelist:
                        print(f"- {file_info.filename}")
                    zip_ref.extractall(data_dir)
                print("解压完成")

                # 删除临时ZIP文件
                if temp_zip.exists():
                    temp_zip.unlink()
                    print("已删除临时ZIP文件")

                # 验证解压结果
                expert_count = len(
                    [f for f in data_dir.iterdir() if f.is_dir()])
                print(f"发现 {expert_count} 个专家目录")

                return True

            except requests.exceptions.RequestException as e:
                print(f"下载失败: {str(e)}")
                return False
            except zipfile.BadZipFile as e:
                print(f"ZIP文件损坏: {str(e)}")
                return False
            except Exception as e:
                print(f"处理文件时出错: {str(e)}")
                return False

        except Exception as e:
            print(f"初始化失败: {str(e)}")
            import traceback
            print("详细错误信息:")
            print(traceback.format_exc())
            return False

    print(f"警告: 未找到 {dropbox_url_key} 配置信息")
    return False


# 页面配置
st.set_page_config(
    page_title="Investment Titans Chat",
    page_icon="📈",
    layout="wide"
)

# 初始化 Dropbox 数据
if 'dropbox_initialized' not in st.session_state:
    st.session_state.dropbox_initialized = initialize_dropbox()

# 如果初始化失败且data目录不存在，显示错误信息
if not st.session_state.dropbox_initialized and not Path("data").exists():
    st.error("无法初始化专家数据。请确保data目录存在或Dropbox配置正确。")
    st.stop()

# 右侧边栏 (移到前面)
with st.sidebar:
    st.header("⚙️ 系统设置")

    # 模型选择
    model_type = st.selectbox(
        "选择模型",
        [
            "gemini-2.0-flash-exp",     # 新的默认选项
            "gemini-exp-1206",
            "gemini-2.0-flash-thinking-exp-1219",
            "deepseek"
        ],
        key="model_type",
        index=0  # 设置默认选项为第一个（现在是 gemini-2.0-flash-exp）
    )

    # 当模型改变时重新创建agents
    if "current_model" not in st.session_state or st.session_state.current_model != model_type:
        st.session_state.agents = create_agents(model_type)
        st.session_state.current_model = model_type
        st.session_state.messages = []  # 清空对话历史
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

# 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agents" not in st.session_state:
    st.session_state.agents = create_agents(model_type)  # 使用已选择的model_type

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
    for i, message in enumerate(st.session_state.messages):
        if message["role"] == "user":
            # 显示用户消息
            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(message["content"])
                if "has_image" in message and message["has_image"]:
                    st.image(message["image"], caption="用户上传的图片",
                             use_container_width=True)
        else:
            # 如果下一条是用户消息或者是最后一条消息，则显示所有agent的回复
            if i == len(st.session_state.messages) - 1 or st.session_state.messages[i + 1]["role"] == "user":
                # 获取当前用户消息的所有agent回复
                agent_responses = [
                    msg for msg in st.session_state.messages[i:i+len(st.session_state.agents)]
                    if msg["role"] == "assistant"
                ]

                # 垂直显示所有回复
                if agent_responses:
                    for response in agent_responses:
                        st.markdown(f"### {response['agent_name']}")
                        with st.chat_message("assistant", avatar=response['avatar']):
                            st.markdown(response["content"])

# 用户输入区域
user_input = st.chat_input("请输入您的问题...")

if user_input:
    # 设置处理状态
    st.session_state.is_processing = True

    # 添加停止按钮
    stop_button = st.button("🛑 停止生成", type="primary")

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
        if stop_button:
            st.session_state.is_processing = False
            st.warning("已停止生成")
            st.rerun()

        if agent_name in st.session_state.selected_experts:
            with st.status(f"{avatar} {agent_name} 正在思考...", expanded=True) as status:
                st.markdown(f"### {agent_name}")
                with st.chat_message("assistant", avatar=avatar):
                    try:
                        response = get_response(
                            agent, user_input, uploaded_image)
                        st.markdown(response)
                        status.update(label=f"{avatar} {
                                      agent_name} 已回答", state="complete")

                        response_data = {
                            "role": "assistant",
                            "content": response,
                            "agent_name": agent_name,
                            "avatar": avatar
                        }
                        st.session_state.messages.append(response_data)
                        expert_responses.append(response_data)
                    except Exception as e:
                        if stop_button:
                            break
                        st.error(f"生成回答时出错: {str(e)}")

    # 如果有多个专家回答，生成总结
    if len(expert_responses) > 1:
        with st.status("🤔 正在生成总结...", expanded=True) as status:
            st.markdown("### 💡 专家观点总结")
            with st.chat_message("assistant", avatar="🎯"):
                # 创建总结agent
                summary_agent = create_summary_agent(model_type)
                summary = get_summary_response(summary_agent, expert_responses)
                st.markdown(summary)
                status.update(label="✨ 总结完成", state="complete")

                # 保存总结到消息历史
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": summary,
                    "agent_name": "专家观点总结",
                    "avatar": "🎯"
                })

    # 重置处理状态
    st.session_state.is_processing = False
