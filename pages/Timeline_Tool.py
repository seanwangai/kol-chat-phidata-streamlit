import streamlit as st
import requests
from datetime import datetime
from typing import List, Dict, Tuple
import json
from google import genai
from google.genai import types
from streamlit_timeline import st_timeline
from itertools import cycle
import pandas as pd

# 页面配置
st.set_page_config(
    page_title="Earnings Call Timeline",
    page_icon="📊",
    layout="wide"
)

# API 配置
API_KEY = st.secrets["API_NINJAS_KEY"]
API_URL = 'https://api.api-ninjas.com/v1/earningstranscript'

# 初始化API密钥轮换
if "api_key_cycle" not in st.session_state:
    st.session_state.api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])

def get_next_api_key():
    """获取下一个API密钥"""
    return next(st.session_state.api_key_cycle)

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
            # !!!!!!!!!
            # for quarter in range(1, 5):
            for quarter in range(4, 5):
                # st.write(f"尝试获取 {year} 年 Q{quarter} 的财报...")

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
        # st.write("开始分析财报内容...")
        if not transcript or len(transcript.strip()) < 100:
            st.warning("财报内容过短或为空，无法进行分析")
            return []

        client = genai.Client(
            api_key=get_next_api_key(),
        )

        prompt = f"""
分析以下财报电话会议记录，提取重点业务主题，是公司重點有提到 和 最後的Q&A分析師關心的主题，就是輸出大家關心的具體業務名就好

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

        # st.write("正在调用 Gemini API...")
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        # 打印原始响应以便调试
        # st.write("Gemini 返回原始响应：", response.candidates[0].content)

        # 尝试从响应中提取文本
        try:
            # 获取响应中的第一个 part 的文本
            response_text = response.candidates[0].content.parts[0].text
            # st.write("解析响应文本：", response_text)

            # 解析 JSON
            # print('主题json')
            # print(response_text)
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


def get_monthly_news(client: genai.Client, company_name: str, topic: str, year: int, month: int) -> List[Dict]:
    """获取特定月份的主题新闻"""
    try:
        prompt = f""" 你是一個專業的投資人，请搜索并总结 "{company_name}" 公司有关於  '{topic}'。在 {year}年{month}月 新發生的新的重大事件和討論區有在討論的，或是發表的新產品，但是如果財報中有說到的就不用了，json event 內文總結成投資人會想看的重點，然後重點先行，以中文回答
注意 一定要跟 '{topic}' 有關的
一定要以JSON格式返回，格式如下:
[{{"date": "2025-01-15","event": "事件简短描述","group": "{topic}"}},]
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
        print('==model res==')
        print(response.candidates[0].content)
        # !!!!!!
        # try:
        #     response_text = response.candidates[0].content.parts[1].text
        #     print('=== in get_monthly_news===')
        #     cleaned_text = response_text.strip()
        #     print(cleaned_text)
        #     print(type(cleaned_text))
        #     return json.loads(cleaned_text)
        # except (AttributeError, json.JSONDecodeError) as e:
        #     print('===GGGGGGG in get_monthly_news===')
        #     print(e)
        #     return []
        response_text = response.candidates[0].content.parts[1].text
        print('=== in get_monthly_news===')
        print(type(response_text))
        # 清理响应文本，移除可能的JSON格式标记
        cleaned_text = response_text.strip()
        if cleaned_text.startswith('```json'):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        print(cleaned_text)
        print(type(cleaned_text))
        return json.loads(cleaned_text)

    except Exception as e:
        print(f"获取 {year}年{month}月新闻时出错: {str(e)}")
        return []


def get_topic_news(topic: str, ticker: str) -> List[Dict]:
    """按月份获取主题的最新消息"""
    try:
        # st.write(f"开始获取 '{topic}' 的月度新闻...")

        client = genai.Client(
            api_key=get_next_api_key(),
        )

        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        all_events = []

        for year in range(2025, current_year + 1):
            end_month = 12 if year < current_year else current_month
            for month in range(1, end_month + 1):
                # st.write(f"正在获取 {year}年{month}月 的新闻...")
                monthly_events = get_monthly_news(client, ticker, topic, year, month)
                all_events.extend(monthly_events)

        return all_events

    except Exception as e:
        st.error(f"获取主题新闻时出错: {str(e)}")
        return []

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
            fetcher = EarningsCallFetcher(API_KEY)
            transcripts = fetcher.get_all_transcripts_since_2024(ticker)

            if transcripts:
                st.session_state.transcripts_data = transcripts
                st.write(f"成功获取 {len(transcripts)} 份财报记录")

                all_transcripts_text = ""
                for transcript_data in transcripts:
                    year = transcript_data['year']
                    quarter = transcript_data['quarter']
                    content = transcript_data['content'].get('transcript', '')
                    if content:
                        all_transcripts_text += f"\n\n=== {year}年 Q{quarter} ===\n{content}"

                st.subheader("🔍 分析所有季度的重点业务主题")
                all_topics = []
                if all_transcripts_text:
                    all_topics = analyze_transcript_topics(all_transcripts_text)
                    print(all_topics)

                    if all_topics:
                        st.success(f"从所有季度中发现 {len(all_topics)} 个主题")
                        # 显示所有发现的主题
                        st.write("📌 发现的主题：")
                        for topic in all_topics:
                            st.markdown(f"- {topic}")

                        st.subheader("📌 重点业务主题分析")
                        
                        # 收集所有主题的事件数据
                        all_events = []
                        groups = []
                        for i, topic in enumerate(all_topics, 1):
                            st.markdown(f"### 🔍 {topic}")
                            with st.spinner(f"正在获取 {topic} 的最新动态..."):
                                events = get_topic_news(topic, ticker)
                                print('==event==') 
                                print(events)
                                all_events.extend(events)
                                
                                # 显示当前主题的事件表格
                                if events:
                                    st.write(f"📋 {topic}相关事件表格：")
                                    # 创建一个更美观的DataFrame
                                    events_df = pd.DataFrame(events)
                                    # 按日期排序
                                    events_df = events_df.sort_values('date')
                                    # 重命名列以便更直观
                                    events_df = events_df[['date', 'event']]
                                    events_df.columns = ["日期", "事件描述"]
                                    # 应用样式并显示
                                    st.dataframe(
                                        events_df,
                                        column_config={
                                            "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                                            "事件描述": st.column_config.TextColumn("事件描述", width="large"),
                                        },
                                        use_container_width=True,
                                        hide_index=True,
                                    )
                                else:
                                    st.info(f"未找到与 {topic} 相关的最新事件")

                                # 为每个主题创建一个分组
                                # 使用现代化的配色方案 - 20种带透明度的单色
                                modern_colors = [
                                    "rgba(65, 88, 208, 0.8)",    # 紫蓝色
                                    "rgba(0, 147, 233, 0.8)",    # 蓝色
                                    "rgba(142, 197, 252, 0.8)",  # 淡蓝色
                                    "rgba(251, 171, 126, 0.8)",  # 橙色
                                    "rgba(133, 255, 189, 0.8)",  # 绿色
                                    "rgba(255, 154, 139, 0.8)",  # 粉红色
                                    "rgba(169, 201, 255, 0.8)",  # 浅蓝色
                                    "rgba(33, 212, 253, 0.8)",   # 青色
                                    "rgba(250, 139, 255, 0.8)",  # 粉色
                                    "rgba(8, 174, 234, 0.8)",    # 蓝绿色
                                    "rgba(254, 225, 64, 0.8)",   # 黄色
                                    "rgba(255, 60, 172, 0.8)",   # 洋红色
                                    "rgba(255, 154, 158, 0.8)",  # 珊瑚色
                                    "rgba(0, 219, 222, 0.8)",    # 青绿色
                                    "rgba(246, 211, 101, 0.8)",  # 金色
                                    "rgba(252, 207, 49, 0.8)",   # 黄橙色
                                    "rgba(67, 233, 123, 0.8)",   # 绿松石色
                                    "rgba(102, 126, 234, 0.8)",  # 靛蓝色
                                    "rgba(244, 59, 71, 0.8)",    # 红色
                                    "rgba(110, 69, 226, 0.8)",   # 紫色
                                ]
                                color_index = i % len(modern_colors) if modern_colors else 0
                                groups.append({
                                    "id": str(i),
                                    "content": topic,
                                    "style": f"color: white; background: {modern_colors[color_index]}; padding: 8px; border-radius: 6px; font-weight: 500; box-shadow: 0 2px 5px rgba(0,0,0,0.1);"
                                })
                            st.markdown("---")

                        # 转换事件数据为时间轴格式，并按时间排序
                        timeline_items = []
                        for i, event in enumerate(all_events):
                            timeline_items.append({
                                "id": i + 1,
                                "content": event['event'],
                                "start": f"{event['date']}T00:00:00",
                                "group": str(all_topics.index(event['group']) + 1)
                            })
                        # 按时间排序
                        timeline_items.sort(key=lambda x: x['start'])
                        print('==============')
                        print(timeline_items)
                        print('=======groups=======')
                        print(groups)
                        # 显示时间轴
                        st.subheader("📅 事件时间轴")
                        
                        # 根据分组数量和每个分组内的项目数量动态计算时间轴高度
                        # 直接根据项目数量动态调整高度
                        # 为每个项目分配50px的高度，再加上基础高度200px
                        dynamic_height = max(600, len(timeline_items) * 50)
                        
                        timeline = st_timeline(
                            timeline_items,
                            groups=groups,
                            options={
                                "selectable": True,
                                "multiselect": True,
                                "zoomable": True,
                                "verticalScroll": True,
                                "stack": True,
                                "height": dynamic_height,  # 使用动态计算的高度
                                "margin": {"axis": 5, "item": {"vertical": 15}},
                                "groupHeightMode": "fixed",
                                "groupMinWidth": 100,  # 设置分组列的最小宽度
                                "groupMaxWidth": 120,  # 设置分组列的最大宽度
                                "orientation": {"axis": "both", "item": "top"},
                                "align": "left",
                                "itemsAlwaysDraggable": True,
                                "showMajorLabels": True,
                                "showMinorLabels": True
                            }
                        )

                        if timeline:
                            st.write("选中的事件：", timeline)

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

                    else:
                        st.warning("未能从所有季度中提取到主题")

            else:
                st.error("未找到任何财报记录")
