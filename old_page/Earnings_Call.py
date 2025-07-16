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
import re

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
    "gemini-2.0-flash-exp": "Gemini Flash",
    "gemini-2.0-flash-thinking-exp-1219": "Gemini Flash Thinking",
    "gemini-exp-1206": "Gemini 1206",
    "deepseek": "DeepSeek"
}

# 初始化所有必要的 session state 变量


def init_session_state():
    """初始化所有必要的 session state 变量"""
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
    if "transcript_agents" not in st.session_state:
        st.session_state.transcript_agents = []
    if "processing_status" not in st.session_state:
        st.session_state.processing_status = {
            "is_processing": False,
            "current_question": None,
            "completed_agents": set(),
            "has_error": False,
            "expert_responses": []
        }
    print("\n=== Session State 初始化 ===")
    print(f"当前消息数: {len(st.session_state.earnings_chat_messages)}")
    print(f"处理状态: {st.session_state.processing_status}")
    print(f"财报专家数: {len(st.session_state.transcript_agents)}")


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


def get_response(agent: Agent, message: str, max_retries: int = 3) -> str:
    """获取 Agent 的响应"""
    for attempt in range(max_retries + 1):
        try:
            # 在每次请求前更新agent的API key
            if isinstance(agent.model, GeminiOpenAIChat):
                agent.model.api_key = get_next_api_key()
                print(f"使用 API Key: {agent.model.api_key[:10]}...")

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
                raise  # 重新抛出异常，让上层处理


def create_summary_agent(model_type: str) -> Agent:
    """创建总结 Agent"""
    system_prompt = """你是一个总结专家，你的任务是：
1. 分析和总结其他专家对财报的分析
2. 提取每个公司财报分析的核心内容
3. 找出各个公司财报之间的共同点和差异点
4. 给出一个全面的市场趋势总结

请以下面的格式输出：
📝 核心观点总结：
[总结各个公司财报的核心观点]

🔍 共同趋势：
[列出各公司财报显示的共同趋势]

💭 差异点：
[列出各公司表现的主要差异]

🎯 市场展望：
[基于所有财报分析给出的市场展望]
"""

    agent = Agent(
        model=GeminiOpenAIChat(
            id=model_type,
            api_key=get_next_api_key(),
        ),
        system_prompt=system_prompt,
        markdown=True
    )
    return agent


def get_summary_response(summary_agent: Agent, expert_responses: list) -> str:
    """获取总结 Agent 的响应"""
    # 按日期降序排序专家回答
    sorted_responses = sorted(expert_responses, key=lambda x: (x['year'], x['quarter']), reverse=True)
    
    # 构建输入信息
    summary_input = "请总结以下财报分析（按时间从新到旧排序）：\n\n"
    for response in sorted_responses:
        summary_input += f"【{response['company']} {response['year']}年Q{response['quarter']}】的分析：\n{response['content']}\n\n"

    # 获取总结
    try:
        response = summary_agent.run(summary_input)
        return response.content
    except Exception as e:
        print(f"生成总结失败: {str(e)}")
        raise  # 重新抛出异常，让上层处理


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


def create_transcript_agent(transcript_data: dict, company: str, year: int, quarter: int) -> dict:
    """为每个财报创建一个 Agent，返回 agent 信息字典"""
    date = transcript_data.get('date', f"{year}-{quarter*3:02d}-01")
    transcript = transcript_data.get('transcript', '')

    system_prompt = f"""你是 {company} 公司 {year}年第{quarter}季度（{date}）财报电话会议记录的分析专家。
以下是这次电话会议的完整记录：

{transcript}

请基于这次会议记录回答用户的问题。回答时：
1. 只使用本次会议记录中的信息
2. 如果问题超出本次会议记录范围，请明确指出
3. 保持专业、准确、简洁
4. 最後給一個結論
"""

    print(f"\n=== 创建 {company} {year}Q{quarter} ({date}) Transcript Agent ===")
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
        'quarter': quarter,
        'date': date
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

    # 股票代码输入和扩充按钮
    col1, col2 = st.columns([2, 1])
    with col1:
        ticker = st.text_input(
            "尋找同業股票代码",
            placeholder="例如：MSFT",
            key="ticker_input",
            label_visibility="visible"  # 显示标签
        ).upper()
    with col2:
        # 使用空白行对齐
        st.write("")  # 添加一个空行来对齐
        expand_tickers = st.button(
            "尋找",
            type="secondary",
            use_container_width=True  # 使按钮填充整个列宽
        )

    # 如果点击扩充按钮
    if expand_tickers and ticker:
        with st.spinner(f"🔍 正在分析 {ticker} 的相关公司..."):
            try:
                agent = create_research_agent(ticker, 10)  # 固定获取10个竞争对手
                response = agent.run(f"给我 {ticker} 的相关公司股票代码")

                try:
                    # 清理响应内容，确保是有效的 Python 列表格式
                    content = response.content.strip()

                    # 使用正则表达式提取列表内容
                    list_pattern = r'\[(.*?)\]'
                    matches = re.findall(list_pattern, content)
                    if matches:
                        # 使用最后一个匹配的列表（通常是最完整的）
                        content = f"[{matches[-1]}]"

                    # 继续清理内容
                    if content.startswith('```') and content.endswith('```'):
                        content = content[3:-3].strip()
                    if content.startswith('python') or content.startswith('json'):
                        content = content.split('\n', 1)[1].strip()

                    print("原始响应:", response.content)
                    print("提取后的列表:", content)

                    # 尝试解析列表
                    related_tickers = eval(content)

                    # 验证结果是否为列表且包含字符串
                    if not isinstance(related_tickers, list) or not all(isinstance(x, str) for x in related_tickers):
                        raise ValueError("返回格式不正确")

                    # 更新 session state 中的相关股票列表
                    all_tickers = [ticker] + related_tickers
                    if "related_tickers" not in st.session_state:
                        st.session_state.related_tickers = all_tickers
                    else:
                        st.session_state.related_tickers = all_tickers

                    # 自动选择前5个股票
                    st.session_state.selected_tickers = all_tickers[:5]

                    st.success(f"✅ 已找到 {len(related_tickers)} 个相关公司，已自动选择前5个")

                except Exception as e:
                    print(f"解析响应时出错: {str(e)}")
                    print(f"原始响应内容: {response.content}")
                    st.error(f"❌ 解析相关公司时出错")
                    if "related_tickers" not in st.session_state:
                        st.session_state.related_tickers = [ticker]
                        st.session_state.selected_tickers = [ticker]
                    else:
                        st.session_state.related_tickers = [ticker]
                        st.session_state.selected_tickers = [ticker]

            except Exception as e:
                st.error(f"❌ 分析相关公司时出错: {str(e)}")
                if "related_tickers" not in st.session_state:
                    st.session_state.related_tickers = [ticker]
                    st.session_state.selected_tickers = [ticker]
                else:
                    st.session_state.related_tickers = [ticker]
                    st.session_state.selected_tickers = [ticker]

    # 显示相关股票多选框
    if "related_tickers" in st.session_state and st.session_state.related_tickers:
        st.subheader("📊 相关股票")

        # 初始化selected_tickers的session state
        if "selected_tickers" not in st.session_state:
            # 默认选择前5个
            st.session_state.selected_tickers = st.session_state.related_tickers[:5]

        # 添加自定义输入
        custom_ticker = st.text_input(
            "新增其他股票代码",
            placeholder="输入股票代码后按回车，例如：MSFT",
            key="custom_ticker"
        ).upper()

        # 如果输入了新的股票代码
        if custom_ticker:
            if custom_ticker not in st.session_state.related_tickers:
                st.session_state.related_tickers.append(custom_ticker)
                if custom_ticker not in st.session_state.selected_tickers:
                    st.session_state.selected_tickers.append(custom_ticker)
                st.rerun()  # 重新运行以更新界面

        # 多选框
        selected_tickers = st.multiselect(
            "选择要分析的公司",
            st.session_state.related_tickers,
            default=st.session_state.selected_tickers,  # 使用session state中的选择
            max_selections=10,  # 最多选择10个
            help="从列表中选择要分析的公司（最多10个）"
        )
        # 更新session state中的选择
        st.session_state.selected_tickers = selected_tickers

    else:
        st.subheader("📊 相关股票")
        # 初始化session state
        if "selected_tickers" not in st.session_state:
            st.session_state.selected_tickers = []

        # 添加自定义输入
        custom_ticker = st.text_input(
            "输入股票代码",
            placeholder="输入股票代码后按回车，例如：MSFT",
            key="custom_ticker"
        ).upper()

        # 如果输入了股票代码
        if custom_ticker:
            if "related_tickers" not in st.session_state:
                st.session_state.related_tickers = [custom_ticker]
            elif custom_ticker not in st.session_state.related_tickers:
                st.session_state.related_tickers.append(custom_ticker)

            if custom_ticker not in st.session_state.selected_tickers:
                st.session_state.selected_tickers.append(custom_ticker)
            st.rerun()  # 重新运行以更新界面

        # 多选框
        selected_tickers = st.multiselect(
            "选择要分析的公司",
            st.session_state.related_tickers if "related_tickers" in st.session_state else [],
            default=st.session_state.selected_tickers,
            max_selections=10,
            help="从列表中选择要分析的公司（最多10个）"
        )
        # 更新session state中的选择
        st.session_state.selected_tickers = selected_tickers

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

    # 获取按钮
    get_data = st.button("获取逐字稿", type="primary", use_container_width=True)

    # 当点击获取按钮时
    if get_data:
        # 验证输入
        if not selected_tickers:
            st.error("请选择至少一个股票")
        elif not selected_quarters:
            st.error("请至少选择一个季度")
        else:
            # 清空所有状态
            st.session_state.transcript_agents = []
            st.session_state.earnings_chat_messages = []
            st.session_state.api_status = []
            st.session_state.transcripts_data = {}
            st.session_state.company_quarters_info = []
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
if selected_tickers and selected_quarters and st.session_state.should_fetch_data:
    # 重置获取数据标志
    st.session_state.should_fetch_data = False

    # 清空之前的状态记录
    st.session_state.api_status = []

    # 获取并创建所有公司的 transcript agents
    with st.spinner("📝 正在获取财报记录..."):
        for current_ticker in selected_tickers:
            transcripts = fetcher.get_sequential_transcripts(
                current_ticker, selected_quarters)
            if transcripts:  # 只处理有数据的公司
                for year, quarter, transcript_data in transcripts:
                    # 为每个季度创建一个 agent
                    agent_info = create_transcript_agent(
                        transcript_data,
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

    # 按年月分组并排序所有财报
    transcripts_by_month = {}
    for agent in st.session_state.transcript_agents:
        if agent.get('date'):
            date_obj = datetime.strptime(agent['date'], '%Y-%m-%d')
            month_key = date_obj.strftime('%Y年%m月')
            if month_key not in transcripts_by_month:
                transcripts_by_month[month_key] = []
            transcripts_by_month[month_key].append({
                'date_obj': date_obj,
                'company': agent['company'],
                'year': agent['year'],
                'quarter': agent['quarter'],
                'date': agent['date']
            })

    # 按月份降序显示财报
    for month in sorted(transcripts_by_month.keys(), reverse=True):
        st.markdown(f"### {month}")

        # 在每个月内按日期降序排序
        month_transcripts = sorted(transcripts_by_month[month], key=lambda x: x['date_obj'], reverse=True)

        # 显示该月的所有财报
        for transcript_info in month_transcripts:
            company = transcript_info['company']
            year = transcript_info['year']
            quarter = transcript_info['quarter']
            date_str = f"({transcript_info['date']})"
            transcript_key = f"{company}_{year}Q{quarter}"

            if transcript_key in st.session_state.transcripts_data:
                # 统一添加年份和季度信息到标题
                title = f"{company} Earnings Call Transcript {date_str} [{year} Q{quarter}]"
                with st.expander(title):
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
        if message["role"] == "user":
            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(message["content"])
        else:
            # 显示专家回答
            with st.chat_message("assistant", avatar=message.get("avatar", "🤖")):
                if "agent_name" in message:
                    # 显示总结标题
                    st.markdown(f"### {message['agent_name']}")
                elif "company" in message:
                    # 获取日期信息
                    date = message.get('date', '')
                    date_str = f"({date})" if date else ""
                    # 显示公司和季度信息
                    st.markdown(
                        f"### {message['company']} {message['year']}年Q{message['quarter']} {date_str}")
                st.markdown(message["content"])

    # 用户输入
    user_input = st.chat_input("请输入您的问题...")

    if user_input:
        print("\n=== 新用户输入 ===")
        print(f"输入内容: {user_input}")
        print(f"当前处理状态: {st.session_state.processing_status}")

        if not st.session_state.processing_status["is_processing"]:
            print("开始新的处理流程")
            # 重置处理状态
            st.session_state.processing_status = {
                "is_processing": True,
                "current_question": user_input,
                "completed_agents": set(),
                "has_error": False,
                "expert_responses": []
            }

            # 添加用户消息
            st.session_state.earnings_chat_messages.append({
                "role": "user",
                "content": user_input
            })

            print(f"更新后的消息数: {len(st.session_state.earnings_chat_messages)}")
            print("执行 rerun...")
            st.rerun()

    # 如果正在处理中且有未完成的专家
    elif st.session_state.processing_status["is_processing"]:
        print("\n=== 继续处理中的请求 ===")
        print(f"当前消息数: {len(st.session_state.earnings_chat_messages)}")
        print(f"处理状态: {st.session_state.processing_status}")

        user_input = st.session_state.processing_status["current_question"]

        # 获取未完成的专家
        remaining_agents = [agent_info for agent_info in st.session_state.transcript_agents
                            if f"{agent_info['company']}_{agent_info['year']}_{agent_info['quarter']}"
                            not in st.session_state.processing_status["completed_agents"]]

        # 按日期降序排序（最新的先回答）
        remaining_agents.sort(
            key=lambda x: (x.get('date', f"{x['year']}-{x['quarter']*3:02d}-01"), x['company']), reverse=True)

        print(f"待处理专家数: {len(remaining_agents)}")
        print(
            f"已完成专家: {st.session_state.processing_status['completed_agents']}")
        print("处理顺序:")
        for agent in remaining_agents:
            print(f"- {agent['company']} {agent['year']}年Q{agent['quarter']}")

        if remaining_agents:
            for agent_info in remaining_agents:
                agent = agent_info['agent']
                company = agent_info['company']
                year = agent_info['year']
                quarter = agent_info['quarter']
                agent_id = f"{company}_{year}_{quarter}"

                print(f"\n处理专家 {agent_id}")
                with st.status(f"🤔 正在分析 {company} {year}年Q{quarter} 财报...", expanded=False) as status:
                    with st.chat_message("assistant", avatar="📊"):
                        try:
                            response = get_response(agent, user_input)
                            st.markdown(response)
                            status.update(label=f"✅ {company} {year}年Q{
                                          quarter} 分析完成", state="complete", expanded=True)

                            response_data = {
                                "role": "assistant",
                                "content": response,
                                "company": company,
                                "year": year,
                                "quarter": quarter,
                                "date": agent_info.get('date', ''),
                                "avatar": "📊"
                            }

                            print("保存专家回答...")
                            st.session_state.earnings_chat_messages.append(
                                response_data)
                            st.session_state.processing_status["expert_responses"].append(
                                response_data)
                            st.session_state.processing_status["completed_agents"].add(
                                agent_id)

                            print(
                                f"当前消息数: {len(st.session_state.earnings_chat_messages)}")
                            print(
                                f"专家回答数: {len(st.session_state.processing_status['expert_responses'])}")
                            print("执行 rerun...")
                            st.rerun()

                        except Exception as e:
                            print(f"专家回答出错: {str(e)}")
                            error_msg = f"分析 {company} {year}年Q{
                                quarter} 财报时出错: {str(e)}"
                            st.error(error_msg)
                            st.session_state.earnings_chat_messages.append({
                                "role": "assistant",
                                "content": f"❌ {error_msg}",
                                "company": company,
                                "year": year,
                                "quarter": quarter,
                                "date": agent_info.get('date', ''),
                                "avatar": "📊"
                            })
                            st.session_state.processing_status["completed_agents"].add(
                                agent_id)
                            st.session_state.error_count += 1

            # 检查是否需要生成总结
            print("\n=== 检查是否需要生成总结 ===")
            print(
                f"已完成专家数: {len(st.session_state.processing_status['completed_agents'])}")
            print(f"总专家数: {len(st.session_state.transcript_agents)}")
            print(
                f"专家回答数: {len(st.session_state.processing_status['expert_responses'])}")

            if (len(st.session_state.processing_status["completed_agents"]) == len(st.session_state.transcript_agents) and
                len(st.session_state.processing_status["expert_responses"]) > 1 and
                    not st.session_state.processing_status.get("has_summary", False)):

                print("开始生成总结...")
                with st.status("🤔 正在生成总结...", expanded=False) as status:
                    try:
                        summary_agent = create_summary_agent(
                            st.session_state.current_model)
                        summary = get_summary_response(
                            summary_agent, st.session_state.processing_status["expert_responses"])

                        with st.chat_message("assistant", avatar="🎯"):
                            st.markdown("### 💡 专家观点总结")
                            st.markdown(summary)
                        status.update(label="✨ 总结完成",
                                      state="complete", expanded=True)

                        st.session_state.earnings_chat_messages.append({
                            "role": "assistant",
                            "content": summary,
                            "agent_name": "专家观点总结",
                            "avatar": "🎯"
                        })
                        st.session_state.processing_status["has_summary"] = True
                        print("总结已添加到消息历史")
                    except Exception as e:
                        print(f"生成总结出错: {str(e)}")
                        st.error(f"生成总结时出错: {str(e)}")
                    finally:
                        print("重置处理状态...")
                        st.session_state.processing_status = {
                            "is_processing": False,
                            "current_question": None,
                            "completed_agents": set(),
                            "has_error": False,
                            "expert_responses": []
                        }
                        print(
                            f"最终消息数: {len(st.session_state.earnings_chat_messages)}")

        else:
            print("所有专家已完成，重置状态")
            st.session_state.processing_status = {
                "is_processing": False,
                "current_question": None,
                "completed_agents": set(),
                "has_error": False,
                "expert_responses": []
            }
            print(f"最终消息数: {len(st.session_state.earnings_chat_messages)}")

    # 添加底部边距，避免输入框遮挡内容
    st.markdown("<div style='margin-bottom: 100px'></div>",
                unsafe_allow_html=True)
