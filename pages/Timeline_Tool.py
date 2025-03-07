import streamlit as st
import requests
from datetime import datetime
from typing import List, Dict, Tuple
import json
from google import genai
from google.genai import types

# 页面配置
st.set_page_config(
    page_title="Earnings Call Timeline",
    page_icon="📊",
    layout="wide"
)

# API 配置
API_KEY = st.secrets["API_NINJAS_KEY"]
API_URL = 'https://api.api-ninjas.com/v1/earningstranscript'


class EarningsCallFetcher:
    """获取财报电话会议记录的类"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {'X-Api-Key': api_key}

    def get_transcript(self, ticker: str, year: int = None, quarter: int = None) -> dict:
        """获取指定公司和季度的财报电话会议记录"""
        try:
            params = {'ticker': ticker}
            if year is not None:
                params['year'] = year
            if quarter is not None:
                params['quarter'] = quarter

            response = requests.get(
                API_URL,
                headers=self.headers,
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    return data[0]
                return data
            else:
                st.error(f"获取财报失败: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"获取财报时出错: {str(e)}")
            return None

    def get_all_transcripts_since_2024(self, ticker: str) -> List[Dict]:
        """获取从2024年至今的所有财报记录"""
        transcripts = []
        current_year = datetime.now().year

        # 从2024年开始，按年和季度顺序获取
        for year in range(2024, current_year + 1):
            for quarter in range(1, 5):
                st.write(f"尝试获取 {year} 年 Q{quarter} 的财报...")

                transcript = self.get_transcript(ticker, year, quarter)

                # 如果获取失败，说明这个季度的财报还没有，就停止获取
                if not transcript:
                    st.info(f"未找到 {year} 年 Q{quarter} 的财报，停止获取")
                    return transcripts

                transcripts.append({
                    'year': year,
                    'quarter': quarter,
                    'content': transcript
                })
                st.success(f"成功获取 {year} 年 Q{quarter} 的财报")

        return transcripts


def analyze_transcript_topics(transcript: str) -> List[str]:
    """使用 Gemini 分析财报中的重点业务主题"""
    try:
        st.write("开始分析财报内容...")
        if not transcript or len(transcript.strip()) < 100:
            st.warning("财报内容过短或为空，无法进行分析")
            return []

        client = genai.Client(
            api_key=st.secrets["GOOGLE_API_KEY"],
        )

        prompt = f"""
分析以下财报电话会议记录，提取重点业务主题：

{transcript}

请以 JSON 格式返回，格式为：
{{"topic": ["主题1", "主题2", "主题3"]}}
"""

        model = "gemini-2.0-flash-exp"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ]

        generate_content_config = types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                properties={
                    "topic": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.STRING,
                        ),
                    ),
                },
            ),
        )

        st.write("正在调用 Gemini API...")
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        # 打印原始响应以便调试
        st.write("Gemini 返回原始响应：", response.candidates[0].content)

        # 尝试从响应中提取文本
        try:
            # 获取响应中的第一个 part 的文本
            response_text = response.candidates[0].content.parts[0].text
            st.write("解析响应文本：", response_text)

            # 解析 JSON
            response_json = json.loads(response_text)
            return response_json.get("topic", [])

        except AttributeError as e:
            st.error(f"响应格式不正确: {str(e)}")
            # 尝试直接从 content 中获取
            try:
                if hasattr(response.candidates[0].content, "topic"):
                    return response.candidates[0].content.topic
                else:
                    st.error("无法从响应中提取主题")
                    return []
            except Exception as e2:
                st.error(f"备选提取方法也失败: {str(e2)}")
                return []

        except json.JSONDecodeError as e:
            st.error(f"JSON 解析失败: {str(e)}")
            return []

        except Exception as e:
            st.error(f"处理响应时出错: {str(e)}")
            return []

    except Exception as e:
        st.error(f"分析主题时出错: {str(e)}")
        return []


def get_monthly_news(client: genai.Client, company_name: str, topic: str, year: int, month: int) -> str:
    """获取特定月份的主题新闻"""
    try:
        prompt = f"""
请搜索并总结 {company_name} {topic} {year}年{month}月 的重要动态和新闻。
请用中文回复，格式为：
- 日期：事件重點
- 日期：事件重點
- 日期：事件重點
"""
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ]

        tools = [types.Tool(google_search=types.GoogleSearch())]
        generate_content_config = types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            tools=tools,
            response_mime_type="text/plain",
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=contents,
            config=generate_content_config,
        )
        print(response.candidates[0].content)
        try:
            return response.candidates[0].content.parts[1].text
        except AttributeError:
            if hasattr(response.candidates[1], 'text'):
                return response.candidates[1].text
            elif hasattr(response.candidates[1].content, 'text'):
                return response.candidates[1].content.text
            else:
                return "无法获取该月新闻"
    except Exception as e:
        return f"获取 {year}年{month}月新闻时出错: {str(e)}"


def get_topic_news(topic: str, ticker: str) -> str:
    """按月份获取主题的最新消息"""
    try:
        st.write(f"开始获取 '{topic}' 的月度新闻...")

        client = genai.Client(
            api_key=st.secrets["GOOGLE_API_KEY"],
        )

        # 获取当前年月
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        all_news = []

        # 从2025年1月开始到当前月份
        for year in range(2025, current_year + 1):
            # 确定结束月份
            end_month = 12 if year < current_year else current_month

            for month in range(1, end_month + 1):
                st.write(f"正在获取 {year}年{month}月 的新闻...")

                monthly_news = get_monthly_news(
                    client, ticker, topic, year, month)
                if monthly_news and monthly_news != "无法获取该月新闻":
                    all_news.append(f"### {year}年{month}月\n{monthly_news}\n")

        if all_news:
            return "\n".join(all_news)
        else:
            return "未找到相关新闻"

    except Exception as e:
        error_msg = f"获取主题新闻时出错: {str(e)}"
        st.error(error_msg)
        return error_msg


# 初始化 session state
if "transcripts_data" not in st.session_state:
    st.session_state.transcripts_data = {}
if "topics_data" not in st.session_state:
    st.session_state.topics_data = {}

# 主页面
st.title("📊 财报电话会议时间线分析")

# 添加股票代码输入
ticker = st.text_input(
    "输入股票代码（例如：AAPL）",
    key="timeline_ticker_input"
).upper()

if ticker:
    if st.button("📈 分析财报时间线", type="primary"):
        with st.spinner(f"正在获取并分析 {ticker} 的财报记录..."):
            # 获取所有财报
            fetcher = EarningsCallFetcher(API_KEY)
            transcripts = fetcher.get_all_transcripts_since_2024(ticker)

            if transcripts:
                st.session_state.transcripts_data = transcripts
                st.write(f"成功获取 {len(transcripts)} 份财报记录")

                # 合并所有季度的财报内容
                all_transcripts_text = ""
                for transcript_data in transcripts:
                    year = transcript_data['year']
                    quarter = transcript_data['quarter']
                    # 修改这里：从 transcript 字段获取内容
                    content = transcript_data['content'].get('transcript', '')
                    if content:
                        all_transcripts_text += f"\n\n=== {year}年 Q{quarter} ===\n{content}"

                # 首先分析所有季度的主题
                st.subheader("🔍 分析所有季度的重点业务主题")
                all_topics = []
                if all_transcripts_text:
                    all_topics = analyze_transcript_topics(
                        all_transcripts_text)
                    if all_topics:
                        st.success(f"从所有季度中发现 {len(all_topics)} 个主题")

                        # 显示主题分析结果
                        st.subheader("📌 重点业务主题分析")

                        # 使用列布局显示主题和新闻
                        for topic in all_topics:
                            st.markdown(f"### 🔍 {topic}")
                            with st.spinner(f"正在获取 {topic} 的最新动态..."):
                                news = get_topic_news(topic, ticker)
                                st.markdown(news)
                            st.markdown("---")  # 添加分隔线
                    else:
                        st.warning("未能从所有季度中提取到主题")

                # 显示各季度原始内容
                st.subheader("📑 各季度财报详情")
                for transcript_data in transcripts:
                    year = transcript_data['year']
                    quarter = transcript_data['quarter']
                    content = transcript_data['content'].get('transcript', '')

                    with st.expander(f"📅 {year}年 Q{quarter}"):
                        if content:
                            st.write(f"内容长度：{len(content)} 字符")
                            st.markdown(content)
                        else:
                            st.warning("财报内容为空")

                # 显示时间线总结
                if all_topics:
                    st.markdown("---")
                    st.header("📊 主题分析总结")

                    # 显示所有发现的主题
                    st.markdown("### 🎯 发现的重点业务主题")
                    for topic in all_topics:
                        st.markdown(f"- {topic}")

            else:
                st.error("未找到任何财报记录")
