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

# 初始化所有会话状态（只在这里初始化一次）
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_model" not in st.session_state:
    st.session_state.current_model = "gemini-2.0-flash-exp"
if "selected_experts" not in st.session_state:
    st.session_state.selected_experts = []
if "agents" not in st.session_state:
    st.session_state.agents = {}
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False
if "error_count" not in st.session_state:
    st.session_state.error_count = 0
if "custom_prompt_ending" not in st.session_state:
    st.session_state.custom_prompt_ending = ""
    print("初始化 custom_prompt_ending")
if "processing_status" not in st.session_state:
    st.session_state.processing_status = {
        "is_processing": False,
        "current_expert": None,
        "completed_experts": set(),
        "has_summary": False,
        "last_user_input": None
    }
if "research_agent" not in st.session_state:
    st.session_state.research_agent = None
if "should_fetch_data" not in st.session_state:
    st.session_state.should_fetch_data = False
if "retry_counts" not in st.session_state:
    st.session_state.retry_counts = {}
# 设置响应超时时间（秒）
RESPONSE_TIMEOUT = 20
# 最大重试次数
MAX_RETRY_COUNT = 3

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
    # st.header("⚙️ 系统设置")

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

    # prompt_ending输入框
    def on_prompt_ending_change():
        # 保存当前选中的专家
        current_selected_experts = st.session_state.selected_experts if "selected_experts" in st.session_state else []

        # 清空消息
        st.session_state.messages = []
        st.session_state.agents = {}
        st.session_state.research_agent = None
        st.session_state.custom_prompt_ending = st.session_state.custom_prompt_ending_input
        print("提示词已更新：", st.session_state.custom_prompt_ending)  # 添加调试信息

        # 重新创建 agents
        st.session_state.agents = create_agents(
            st.session_state.current_model,
            lazy_loading=True,
            custom_prompt_ending=st.session_state.custom_prompt_ending
        )

        # 恢复之前选中的专家
        st.session_state.selected_experts = [
            expert for expert in current_selected_experts if expert in st.session_state.agents]

        # 如果没有选中的专家，默认选择所有专家
        if not st.session_state.selected_experts:
            st.session_state.selected_experts = list(
                st.session_state.agents.keys())

    custom_prompt_ending = st.text_area(
        "自定义提示词结尾",
        value=st.session_state.custom_prompt_ending,
        key="custom_prompt_ending_input",
        help="如果不填写，将使用默认的提示词结尾",
        on_change=on_prompt_ending_change
    )

    # 确保值被正确设置
    if custom_prompt_ending:
        if st.session_state.custom_prompt_ending != custom_prompt_ending:
            st.session_state.custom_prompt_ending = custom_prompt_ending
            print("更新 custom_prompt_ending：", custom_prompt_ending)
            # 强制重新创建 agents
            st.session_state.agents = create_agents(
                st.session_state.current_model,
                lazy_loading=True,
                custom_prompt_ending=custom_prompt_ending
            )

    # 当模型改变时重新创建agents
    if st.session_state.current_model != model_type:
        st.session_state.current_model = model_type
        st.session_state.messages = []
        st.session_state.agents = {}
        st.session_state.research_agent = None
        st.rerun()

    # 如果还没有创建agents，现在创建
    if not st.session_state.agents:
        st.session_state.agents = create_agents(
            model_type, lazy_loading=True, custom_prompt_ending=custom_prompt_ending)
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
    for agent_name, (agent, avatar, expert_folder) in st.session_state.agents.items():
        col1, col2 = st.columns([0.7, 3])
        with col1:
            # 使用之前保存的选择状态
            is_selected = agent_name in st.session_state.selected_experts
            if st.checkbox(
                label=f"选择{agent_name}",
                value=is_selected,
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
                st.session_state.research_agent = None  # 重置研究 agent
                st.success("专家资料更新成功！")
                st.rerun()
            else:
                st.error("更新失败，请检查网络连接或配置。")

# 删除重复的初始化代码
# 页面标题
st.title("📈 Investment Titans Chat")

# 在用户输入区域之前添加图片和PDF上传
uploaded_image = None
uploaded_pdf_content = None
if model_type.startswith("gemini"):
    uploaded_file = st.file_uploader(
        "上传图片或PDF文件（可选）", type=['png', 'jpg', 'jpeg', 'pdf'])
    if uploaded_file is not None:
        # 根据文件扩展名判断文件类型
        file_extension = uploaded_file.name.split('.')[-1].lower()

        if file_extension == 'pdf':
            # 处理PDF文件
            try:
                from utils import read_pdf
                import fitz  # PyMuPDF
                import io

                # 读取PDF文件内容
                pdf_bytes = uploaded_file.read()
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

                # 显示PDF信息
                st.write(
                    f"📄 PDF文件: {uploaded_file.name} ({pdf_document.page_count} 页)")

                # 提取PDF文本内容
                pdf_text = ""
                for page in pdf_document:
                    pdf_text += page.get_text()

                # 存储PDF内容以供后续使用
                uploaded_pdf_content = pdf_text
                print(pdf_text)

                # 显示PDF预览（仅显示第一页）
                first_page = pdf_document[0]
                pix = first_page.get_pixmap()
                img_data = pix.tobytes("png")
                # st.image(
                #     img_data, caption=f"PDF预览 (第1页，共{pdf_document.page_count}页)", use_container_width=True)

            except Exception as e:
                st.error(f"读取PDF文件失败: {str(e)}")
        else:
            # 处理图片文件
            st.image(uploaded_file, caption="已上传的图片", use_container_width=True)
            uploaded_image = uploaded_file.getvalue()

# 左侧聊天区域
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

# 用户输入处理
if user_input and not st.session_state.processing_status["is_processing"]:
    # 重置处理状态
    st.session_state.processing_status = {
        "is_processing": True,
        "current_expert": None,
        "completed_experts": set(),
        "has_summary": False,
        "last_user_input": user_input
    }

    # 添加用户消息
    message_data = {
        "role": "user",
        "content": user_input,
    }
    if uploaded_image:
        message_data["has_image"] = True
        message_data["image"] = uploaded_image
    elif uploaded_pdf_content:
        # 如果有PDF内容，将其添加到用户消息中
        message_data[
            "content"] = f"{user_input}\n\n[PDF内容]:\n{uploaded_pdf_content[:2000]}...(PDF内容已截断)"
        message_data["has_pdf"] = True
    st.session_state.messages.append(message_data)

    # 立即重新运行以显示用户消息
    st.rerun()

# 如果正在处理中且有未完成的专家
elif st.session_state.processing_status["is_processing"]:
    user_input = st.session_state.processing_status["last_user_input"]

    # 获取选中的专家列表
    selected_experts = [name for name in st.session_state.selected_experts
                        if name not in st.session_state.processing_status["completed_experts"]]

    if selected_experts:
        expert_responses = []

        # 继续处理未完成的专家
        for agent_name, (agent, avatar, _) in st.session_state.agents.items():
            if agent_name in selected_experts:
                with st.status(f"{avatar} {agent_name} 正在思考...", expanded=False) as status:
                    with st.chat_message("assistant", avatar=avatar):
                        try:
                            # 初始化重试计数
                            if agent_name not in st.session_state.retry_counts:
                                st.session_state.retry_counts[agent_name] = 0

                            # 设置超时标志
                            response_timeout = False
                            response = None

                            # 使用超时机制获取响应
                            try:
                                import threading
                                import time

                                # 创建一个事件用于通知超时
                                timeout_event = threading.Event()
                                response_ready = threading.Event()
                                response_container = [None]

                                # 定义获取响应的线程函数
                                def get_response_with_timeout():
                                    try:
                                        # 传递完整的元组(agent, avatar, expert_folder)给get_response函数
                                        agent_tuple = (agent, avatar, _)
                                        # 根据上传的内容类型调用不同的处理方式
                                        if uploaded_pdf_content:
                                            # 如果有PDF内容，将其作为文本传递给模型
                                            result = get_response(
                                                agent_tuple,
                                                user_input,
                                                None,
                                                pdf_content=uploaded_pdf_content,
                                                custom_prompt_ending=custom_prompt_ending  # 直接传入
                                            )
                                        else:
                                            # 否则使用原有的图片处理方式
                                            result = get_response(
                                                agent_tuple,
                                                user_input,
                                                uploaded_image,
                                                custom_prompt_ending=custom_prompt_ending  # 直接传入
                                            )
                                        if not timeout_event.is_set():
                                            response_container[0] = result
                                            response_ready.set()
                                    except Exception as e:
                                        if not timeout_event.is_set():
                                            response_container[0] = f"错误: {str(e)}"
                                            response_ready.set()

                                # 启动响应线程
                                response_thread = threading.Thread(
                                    target=get_response_with_timeout)
                                response_thread.daemon = True
                                response_thread.start()

                                # 等待响应或超时
                                start_time = time.time()
                                status.update(
                                    label=f"{avatar} {agent_name} 正在思考... (0/{RESPONSE_TIMEOUT}秒)", state="running")

                                # 更新进度条
                                while not response_ready.is_set() and time.time() - start_time < RESPONSE_TIMEOUT:
                                    elapsed = int(time.time() - start_time)
                                    status.update(
                                        label=f"{avatar} {agent_name} 正在思考... ({elapsed}/{RESPONSE_TIMEOUT}秒)", state="running")
                                    time.sleep(1)

                                # 检查是否超时
                                if not response_ready.is_set():
                                    timeout_event.set()
                                    response_timeout = True
                                    status.update(
                                        label=f"⏱️ {agent_name} 响应超时", state="error")
                                else:
                                    response = response_container[0]

                            except Exception as e:
                                st.error(f"执行超时检测时出错: {str(e)}")

                            # 处理超时情况
                            if response_timeout:
                                # 增加重试计数
                                st.session_state.retry_counts[agent_name] += 1

                                # 检查是否达到最大重试次数
                                if st.session_state.retry_counts[agent_name] <= MAX_RETRY_COUNT:
                                    status.update(
                                        label=f"🔄 {agent_name} 正在重试... (第{st.session_state.retry_counts[agent_name]}次)", state="running")
                                    st.warning(
                                        f"{agent_name} 响应超时，正在重试... (第{st.session_state.retry_counts[agent_name]}/{MAX_RETRY_COUNT}次)")
                                    # 不标记为已完成，允许在下一个循环中重试
                                    continue
                                else:
                                    # 达到最大重试次数，标记为失败
                                    error_msg = f"响应超时，已重试{MAX_RETRY_COUNT}次"
                                    st.error(error_msg)
                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": f"❌ {error_msg}",
                                        "agent_name": agent_name,
                                        "avatar": avatar
                                    })
                                    # 标记该专家已完成（超过最大重试次数）
                                    st.session_state.processing_status["completed_experts"].add(
                                        agent_name)
                                    st.session_state.error_count += 1
                                    continue

                            # 正常响应处理
                            if response and not response.startswith("错误:"):
                                st.markdown(response)
                                status.update(
                                    label=f"✅ {agent_name} 已回答", state="complete", expanded=True)

                                # 重置重试计数
                                st.session_state.retry_counts[agent_name] = 0

                                response_data = {
                                    "role": "assistant",
                                    "content": response,
                                    "agent_name": agent_name,
                                    "avatar": avatar
                                }
                                st.session_state.messages.append(response_data)
                                expert_responses.append(response_data)

                                # 标记该专家已完成
                                st.session_state.processing_status["completed_experts"].add(
                                    agent_name)
                            else:
                                # 处理错误响应
                                error_msg = response if response else "生成回答时出错"
                                st.error(error_msg)
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": f"❌ {error_msg}",
                                    "agent_name": agent_name,
                                    "avatar": avatar
                                })
                                # 标记该专家已完成（即使出错）
                                st.session_state.processing_status["completed_experts"].add(
                                    agent_name)
                                st.session_state.error_count += 1

                        except Exception as e:
                            error_msg = f"生成回答时出错: {str(e)}"
                            st.error(error_msg)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"❌ {error_msg}",
                                "agent_name": agent_name,
                                "avatar": avatar
                            })
                            # 标记该专家已完成（即使出错）
                            st.session_state.processing_status["completed_experts"].add(
                                agent_name)
                            st.session_state.error_count += 1

        # 如果所有专家都已完成且需要生成总结
        if len(st.session_state.processing_status["completed_experts"]) == len(st.session_state.selected_experts) and \
           len(expert_responses) > 1 and not st.session_state.processing_status["has_summary"]:
            with st.status("🤔 正在生成总结...", expanded=False) as status:
                try:
                    summary_agent = create_summary_agent(
                        st.session_state.current_model)
                    summary = get_summary_response(
                        summary_agent, expert_responses)

                    with st.chat_message("assistant", avatar="🎯"):
                        st.markdown("### 💡 专家观点总结")
                        st.markdown(summary)
                    status.update(label="✨ 总结完成",
                                  state="complete", expanded=True)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": summary,
                        "agent_name": "专家观点总结",
                        "avatar": "🎯"
                    })
                    st.session_state.processing_status["has_summary"] = True
                except Exception as e:
                    st.error(f"生成总结时出错: {str(e)}")
                finally:
                    # 所有处理完成，重置状态
                    st.session_state.processing_status["is_processing"] = False

    else:
        # 所有专家都已完成，重置状态
        st.session_state.processing_status["is_processing"] = False

# 添加底部边距
st.markdown("<div style='margin-bottom: 100px'></div>", unsafe_allow_html=True)
