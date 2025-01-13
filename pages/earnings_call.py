import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import json
from typing import List, Tuple, Dict
from phi.agent import Agent
from phi.model.google import GeminiOpenAIChat
from itertools import cycle
import random

# 页面配置
st.set_page_config(
    page_title="Earnings Call Transcripts",
    page_icon="🎙️",
    layout="wide"
)

# API 配置
API_KEY = st.secrets["API_NINJAS_KEY"]  # 从 secrets 中获取 API key
API_URL = 'https://api.api-ninjas.com/v1/earningstranscript'

# 定义可用的 emoji 列表
SPEAKER_EMOJIS = ["👨‍💼", "👩‍💼", "👨‍💻", "👩‍💻", "👨‍🔬", "👩‍🔬", "🧑‍💼", "🧑‍💻", "👨‍🏫", "👩‍🏫",
                  "👨‍⚖️", "👩‍⚖️", "👨‍🚀", "👩‍🚀", "🤵", "👔", "👩‍🦰", "👨‍🦰", "👱‍♂️", "👱‍♀️"]

# 定义可用的模型
MODELS = {
    "gemini-2.0-flash-thinking-exp-1219": "Gemini Flash Thinking",
    "gemini-2.0-flash-exp": "Gemini Flash",
    "gemini-exp-1206": "Gemini 1206",
    "deepseek": "DeepSeek"
}

# 初始化所有必要的 session state 变量


def init_session_state():
    """初始化所有必要的 session state 变量"""
    if "transcript_agents" not in st.session_state:
        st.session_state.transcript_agents = []
    if "earnings_chat_messages" not in st.session_state:
        st.session_state.earnings_chat_messages = []
    if "api_status" not in st.session_state:
        st.session_state.api_status = []
    if "transcripts_data" not in st.session_state:
        st.session_state.transcripts_data = {}
    if "current_model" not in st.session_state:
        st.session_state.current_model = "gemini-2.0-flash-exp"
    if "company_quarters_info" not in st.session_state:
        st.session_state.company_quarters_info = []
    if "competitor_count" not in st.session_state:
        st.session_state.competitor_count = 3
    if "api_key_cycle" not in st.session_state:
        st.session_state.api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])


# 确保在页面开始时就初始化所有状态
init_session_state()


def process_transcript_text(text: str) -> str:
    """处理财报文本，转换为 Markdown 格式，并为说话人添加 emoji"""
    # 创建说话人到 emoji 的映射
    speaker_emoji_map = {}
    available_emojis = SPEAKER_EMOJIS.copy()

    # 处理特殊符号的函数
    def replace_special_chars(text: str) -> str:
        replacements = {
            '*': '＊',    # 全角星号
            '#': '＃',    # 全角井号
            '[': '［',    # 全角方括号
            ']': '］',    # 全角方括号
            '`': '｀',    # 全角反引号
            '_': '＿',    # 全角下划线
            '~': '～',    # 全角波浪线
            '>': '＞',    # 全角大于号
            '<': '＜',    # 全角小于号
            '|': '｜',    # 全角竖线
            '\\': '＼',   # 全角反斜线
            '{': '｛',    # 全角花括号
            '}': '｝',    # 全角花括号
            '(': '（',    # 全角圆括号
            ')': '）',    # 全角圆括号
            '$': '＄',    # 全角圆括号
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    sentences = []
    current_sentence = []

    # 按行分割，处理每一行
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 如果是新的对话（包含冒号），开始新的句子
        if ':' in line and len(line.split(':')[0].split()) <= 3:
            # 如果有未完成的句子，先保存
            if current_sentence:
                processed_text = replace_special_chars(
                    ' '.join(current_sentence))
                sentences.append(processed_text)
                current_sentence = []

            # 处理新的对话
            parts = line.split(':', 1)
            speaker = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""

            # 处理内容中的特殊字符
            content = replace_special_chars(content)

            # 为说话人分配 emoji（如果还没有）
            if speaker not in speaker_emoji_map:
                if available_emojis:
                    emoji = random.choice(available_emojis)
                    available_emojis.remove(emoji)
                else:
                    available_emojis = SPEAKER_EMOJIS.copy()
                    emoji = random.choice(available_emojis)
                    available_emojis.remove(emoji)
                speaker_emoji_map[speaker] = emoji

            # 添加带 emoji 的说话人和内容
            sentences.append(
                f"{speaker_emoji_map[speaker]} **{speaker}**: {content}")
        else:
            # 继续当前句子
            current_sentence.append(line)

    # 处理最后一个未完成的句子
    if current_sentence:
        processed_text = replace_special_chars(' '.join(current_sentence))
        sentences.append(processed_text)

    # 用双换行连接所有处理后的句子
    return "\n\n".join(sentences)


# 定义可选的季度（按时间顺序）
AVAILABLE_QUARTERS = [
    (2024, 1), (2024, 2),  # 添加 Q1、Q2，默认不选
    (2024, 3), (2024, 4),  # 从 Q3 开始默认选中
    (2025, 1), (2025, 2), (2025, 3), (2025, 4)
]

# 默认选中的季度
DEFAULT_SELECTED = [
    (2024, 3), (2024, 4),
    (2025, 1), (2025, 2), (2025, 3), (2025, 4)
]


def get_next_api_key():
    """获取下一个 API key"""
    return next(st.session_state.api_key_cycle)


def create_research_agent(ticker: str, competitor_count: int) -> Agent:
    """创建研究 Agent"""
    system_prompt = f"""你是一个专业的股票研究助手。你需要列出与 {ticker} 公司相關的 {competitor_count} 個竞争对手或同行业公司的股票代码。

请注意：
1. 只返回股票代码列表，是美股 ticker
2. 确保返回的是实际存在的股票代码
3. 格式必须是 list，就算只有1個還是要return list
4. 只返回代码，不要有任何解释或其他文字
5. 必须返回 {competitor_count} 个代码

例如，如果输入是 "AMAT"，你应该只返回类似这样的内容：
["LRCX", "KLAC", "TSMC"]"""

    print("\n=== 创建研究 Agent ===")
    print(f"使用模型: {st.session_state.current_model}")
    print(f"System Prompt: {system_prompt}")

    agent = Agent(
        model=GeminiOpenAIChat(
            id=st.session_state.current_model,
            api_key=get_next_api_key(),
        ) if st.session_state.current_model != "deepseek" else DeepSeekChat(
            api_key=st.secrets["DEEPSEEK_API_KEY"],
        ),
        system_prompt=system_prompt,
        markdown=True
    )

    # 打印 agent 的配置
    print("\nAgent 配置:")
    print(f"Model Type: {type(agent.model).__name__}")
    print(f"System Prompt: {agent.system_prompt}")
    return agent


def create_transcript_agent(transcript: str, company: str, year: int, quarter: int) -> dict:
    """为每个财报创建一个 Agent，返回 agent 信息字典"""
    system_prompt = f"""你是 {company} 公司 {year}年第{quarter}季度财报电话会议记录的分析专家。
以下是这次电话会议的完整记录：

{transcript}

请基于这次会议记录回答用户的问题。回答时：
1. 只使用本次会议记录中的信息
2. 如果问题超出本次会议记录范围，请明确指出
3. 保持专业、准确、简洁
4. 最後給一個結論
"""

    print(f"\n=== 创建 {company} {year}Q{quarter} Transcript Agent ===")
    print(f"使用模型: {st.session_state.current_model}")
    print(f"System Prompt: {system_prompt[:200]}...")  # 只打印前200个字符

    agent = Agent(
        model=GeminiOpenAIChat(
            id=st.session_state.current_model,
            api_key=get_next_api_key(),
        ) if st.session_state.current_model != "deepseek" else DeepSeekChat(
            api_key=st.secrets["DEEPSEEK_API_KEY"],
        ),
        system_prompt=system_prompt,
        markdown=True
    )

    # 打印 agent 的配置
    print("\nAgent 配置:")
    print(f"Model Type: {type(agent.model).__name__}")
    print(f"System Prompt Length: {len(agent.system_prompt)}")

    return {
        'agent': agent,
        'company': company,
        'year': year,
        'quarter': quarter
    }


class EarningsCallFetcher:
    def __init__(self, api_key):
        self.headers = {'X-Api-Key': api_key}

    def get_transcript(self, ticker: str, year: int, quarter: int) -> dict:
        """获取指定季度的财报电话会议记录"""
        try:
            response = requests.get(
                API_URL,
                headers=self.headers,
                params={
                    'ticker': ticker,
                    'year': year,
                    'quarter': quarter
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"获取数据失败: {str(e)}")
            if hasattr(e.response, 'text'):
                st.error(f"错误详情: {e.response.text}")
            return None

    def get_sequential_transcripts(self, ticker: str, selected_quarters: List[Tuple[int, int]]) -> List[Tuple[int, int, Dict]]:
        """按选定的季度获取财报记录，遇到空记录停止"""
        results = []

        # 按时间顺序排序选定的季度
        sorted_quarters = sorted(selected_quarters, key=lambda x: (x[0], x[1]))

        with st.spinner(f"正在获取 {ticker} 的财报记录..."):
            for year, quarter in sorted_quarters:
                transcript = self.get_transcript(ticker, year, quarter)

                # 如果返回为空或没有 transcript 字段，停止获取
                if not transcript or 'transcript' not in transcript:
                    return results

                results.append((year, quarter, transcript))

        return results


# 创建实例
fetcher = EarningsCallFetcher(API_KEY)

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 设置")

    # 股票代码输入和获取按钮
    col1, col2 = st.columns([3, 1])
    with col1:
        ticker = st.text_input("股票代码", placeholder="例如：MSFT",
                               key="ticker_input", on_change=None).upper()

    # 季度选择
    st.subheader("📅 选择季度")
    selected_quarters = []
    for year, quarter in AVAILABLE_QUARTERS:
        # 检查是否在默认选中列表中
        default_value = (year, quarter) in DEFAULT_SELECTED
        if st.checkbox(f"{year} Q{quarter}", value=default_value, key=f"quarter_{year}_{quarter}"):
            selected_quarters.append((year, quarter))

    if not selected_quarters:
        st.warning("请至少选择一个季度")

    # 竞争对手数量选择
    competitor_count = st.number_input(
        "选择竞争对手数量",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
        help="选择要分析的相关公司数量"
    )

    # 获取按钮
    get_data = st.button("获取逐字稿", type="primary", use_container_width=True)

    # 当点击获取按钮时
    if get_data:
        # 验证输入
        if not ticker:
            st.error("请输入股票代码")
        elif not selected_quarters:
            st.error("请至少选择一个季度")
        else:
            # 清空所有状态
            st.session_state.transcript_agents = []
            st.session_state.earnings_chat_messages = []
            st.session_state.api_status = []
            st.session_state.transcripts_data = {}
            st.session_state.company_quarters_info = []
            # 保存当前的竞争对手数量
            st.session_state.competitor_count = competitor_count
            # 设置标志表示需要获取数据
            st.session_state.should_fetch_data = True
            st.rerun()

    st.markdown("---")

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
        # 只有在已经有 agents 时才清空
        if st.session_state.transcript_agents:
            st.session_state.transcript_agents = []
            st.session_state.earnings_chat_messages = []
            st.session_state.company_quarters_info = []
            st.info("已切换模型，请重新输入股票代码获取财报。")

# 主页面
st.title("🎙️ Earnings Call Transcripts")

# 创建容器
api_status_container = st.container()  # 用于显示 API 状态

# 显示 API 状态记录
with api_status_container:
    for status_msg in st.session_state.api_status:
        st.markdown(status_msg)

# 初始化 should_fetch_data
if 'should_fetch_data' not in st.session_state:
    st.session_state.should_fetch_data = False

# 处理股票代码输入和 agent 创建
if ticker and selected_quarters and st.session_state.should_fetch_data:
    # 重置获取数据标志
    st.session_state.should_fetch_data = False

    # 清空之前的状态记录
    st.session_state.api_status = []

    # 创建研究 agent 并获取相关公司
    with st.spinner("🔍 正在分析相关公司..."):
        try:
            # 使用保存的竞争对手数量
            current_competitor_count = getattr(
                st.session_state, 'competitor_count', competitor_count)
            agent = create_research_agent(ticker, current_competitor_count)
            response = agent.run(f"给我 {ticker} 的相关公司股票代码")

            # 打印原始响应内容以便调试
            print('原始响应:', response.content)

            try:
                # 清理响应内容，确保是有效的 Python 列表格式
                content = response.content.strip()
                # 如果内容被反引号包围，去除它们
                if content.startswith('```') and content.endswith('```'):
                    content = content[3:-3].strip()
                # 如果内容包含 python 或 json 标记，去除它
                if content.startswith('python') or content.startswith('json'):
                    content = content.split('\n', 1)[1].strip()

                # 尝试解析列表
                related_tickers = eval(content)

                # 验证结果是否为列表且包含字符串
                if not isinstance(related_tickers, list) or not all(isinstance(x, str) for x in related_tickers):
                    raise ValueError("返回格式不正确")

                print('处理后的相关公司:', related_tickers)
                all_tickers = [ticker] + related_tickers
            except Exception as e:
                print(f"解析响应时出错: {str(e)}")
                print(f"原始响应内容: {response.content}")
                st.error(f"❌ 解析相关公司时出错，将只分析输入的公司")
                all_tickers = [ticker]

        except Exception as e:
            st.error(f"❌ 分析相关公司时出错: {str(e)}")
            all_tickers = [ticker]

    # 获取并创建所有公司的 transcript agents
    with st.spinner("📝 正在获取财报记录..."):
        for current_ticker in all_tickers:
            transcripts = fetcher.get_sequential_transcripts(
                current_ticker, selected_quarters)
            if transcripts:  # 只处理有数据的公司
                for year, quarter, transcript_data in transcripts:
                    # 为每个季度创建一个 agent
                    agent_info = create_transcript_agent(
                        transcript_data['transcript'],
                        current_ticker,
                        year,
                        quarter
                    )
                    st.session_state.transcript_agents.append(agent_info)

                    # 保存财报原文
                    transcript_key = f"{current_ticker}_{year}Q{quarter}"
                    raw_text = transcript_data['transcript']
                    st.session_state.transcripts_data[transcript_key] = raw_text

        if st.session_state.transcript_agents:
            # 整理每个公司的季度信息
            company_quarters = {}
            for agent_info in st.session_state.transcript_agents:
                company = agent_info['company']
                year = agent_info['year']
                quarter = agent_info['quarter']
                if company not in company_quarters:
                    company_quarters[company] = []
                company_quarters[company].append(f"{year}Q{quarter}")

            # 显示成功信息
            st.success(
                f"✅ 已获取 {len(st.session_state.transcript_agents)} 份财报记录")

            # 保存和显示每个公司的季度详情
            company_details = []
            for company, quarters in company_quarters.items():
                quarters.sort()  # 按时间顺序排序
                company_details.append(
                    f"- {company}: {', '.join(quarters)}")

            # 保存到 session_state
            st.session_state.company_quarters_info = company_details
            st.markdown("\n".join(company_details))
        else:
            st.warning("⚠️ 未找到任何可用的财报记录")

# 只有在有 agents 时才显示问答区域
if st.session_state.transcript_agents:
    # 添加财报原文显示区域
    st.markdown("## 📄 财报原文")

    # 获取所有唯一的年份和季度组合，按时间倒序排序
    year_quarters = sorted(set((agent['year'], agent['quarter'])
                               for agent in st.session_state.transcript_agents),
                           reverse=True)

    # 对于每个季度
    for year, quarter in year_quarters:
        st.markdown(f"### {year} Q{quarter}")

        # 找到这个季度的所有公司
        quarter_companies = sorted(set(
            agent['company'] for agent in st.session_state.transcript_agents
            if agent['year'] == year and agent['quarter'] == quarter
        ))

        # 为每个公司创建下拉框
        for company in quarter_companies:
            transcript_key = f"{company}_{year}Q{quarter}"
            if transcript_key in st.session_state.transcripts_data:
                with st.expander(f"{company} Earnings Call Transcript"):
                    st.markdown("#### 原文内容")
                    # 处理文本格式
                    raw_text = st.session_state.transcripts_data[transcript_key]
                    formatted_text = process_transcript_text(raw_text)
                    st.markdown(formatted_text)

    st.markdown("---")  # 添加分隔线

    # 问答区域
    st.markdown("## 💬 问答区域")

    # 显示公司季度信息
    if st.session_state.company_quarters_info:
        st.markdown("### 📊 已获取的财报记录")
        st.markdown("\n".join(st.session_state.company_quarters_info))
        st.markdown("---")

    # 显示聊天历史
    for message in st.session_state.earnings_chat_messages:
        with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🤖"):
            st.markdown(message["content"])

    # 用户输入
    user_input = st.chat_input("请输入您的问题...")

    # 处理新的用户输入
    if user_input:
        # 添加用户消息
        st.session_state.earnings_chat_messages.append({
            "role": "user",
            "content": user_input
        })

        # 显示用户消息
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input)

        # 获取所有唯一的年份和季度组合，按时间倒序排序
        year_quarters = sorted(set((agent['year'], agent['quarter'])
                                   for agent in st.session_state.transcript_agents),
                               reverse=True)

        # 收集所有回答
        all_responses = []

        # 对于每个季度
        for year, quarter in year_quarters:
            # 添加季度标题
            all_responses.append(f"## 📅 {year} Q{quarter} 分析\n")

            # 找到这个季度的所有公司的 agents
            quarter_agents = [
                agent for agent in st.session_state.transcript_agents
                if agent['year'] == year and agent['quarter'] == quarter
            ]

            # 按公司名称排序
            quarter_agents.sort(key=lambda x: x['company'])

            # 获取每个公司这个季度的回答
            for agent_info in quarter_agents:
                try:
                    with st.status(f"🤔 {agent_info['company']} - {year}Q{quarter} 正在分析...", expanded=False) as status:
                        response = agent_info['agent'].run(user_input)
                        status.update(label=f"✅ {
                                      agent_info['company']} - {year}Q{quarter} 分析完成", state="complete", expanded=True)

                        # 添加公司回答
                        response_text = f"### 🏢 {
                            agent_info['company']} - {year}Q{quarter}\n{response.content}\n---\n"
                        all_responses.append(response_text)

                        # 显示当前回答
                        with st.chat_message("assistant", avatar="🤖"):
                            st.markdown(response_text)

                except Exception as e:
                    print(f"错误: {str(e)}")
                    print(f"错误类型: {type(e)}")
                    continue

            # 在每个季度的分析后添加额外的分隔
            all_responses.append("---\n")

        # 将所有回答合并为一个字符串
        complete_response = "\n".join(all_responses)

        # 保存完整回答到会话状态
        st.session_state.earnings_chat_messages.append({
            "role": "assistant",
            "content": complete_response
        })

    # 添加底部边距，避免输入框遮挡内容
    st.markdown("<div style='margin-bottom: 100px'></div>",
                unsafe_allow_html=True)
