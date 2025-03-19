import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar
from collections import Counter
import json
import time
import os
import base64
# import google.generativeai as genai
from google import genai
from google.genai import types
from exa_py import Exa
from dateutil.relativedelta import relativedelta
import streamlit.components.v1 as components
import concurrent.futures

# 頁面配置
st.set_page_config(
    page_title="Timeline AI",
    page_icon="📊",
    layout="wide"
)

# 初始化 Exa 客戶端
@st.cache_resource
def get_exa_client():
    return Exa(api_key=st.secrets["EXA_API_KEY"])

# 設置 Gemini API
def get_gemini_client():
    """獲取 Gemini API 客戶端"""
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if not api_key:
        st.error("未找到 Gemini API Key，請在 .streamlit/secrets.toml 中設置 GEMINI_API_KEY")
        return None
    
    return genai.Client(api_key=api_key)

# 獲取當前日期和12個月前的日期
def get_default_dates():
    today = datetime.now()
    twelve_months_ago = today - relativedelta(months=12)
    
    # 設置為12個月前的第一天
    start_date = twelve_months_ago.replace(day=1)
    
    return start_date, today

# 生成月份列表
def generate_month_ranges(start_date, end_date):
    months = []
    current_date = start_date
    
    while current_date <= end_date:
        # 獲取當月的最後一天
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        month_end = current_date.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        
        # 如果月末超過了結束日期，則使用結束日期
        if month_end > end_date:
            month_end = end_date
            
        months.append({
            'start': current_date,
            'end': month_end,
            'name': current_date.strftime('%Y-%m')
        })
        
        # 移動到下個月的第一天
        current_date = (month_end + timedelta(days=1)).replace(day=1)
        
    return months

# 格式化日期為 ISO 8601 格式 (UTC)
def format_date_for_api(date):
    # 轉換為 UTC 時間
    return date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# 從 Exa 結果中提取數據
def extract_data_from_result(result):
    """從 Exa API 結果中提取數據，處理不同的結果格式"""
    data = {}
    
    # 檢查是否為字典類型
    if isinstance(result, dict):
        return extract_data_from_dict(result)
    
    # 嘗試直接訪問屬性
    if hasattr(result, 'title'):
        data['title'] = result.title
    elif hasattr(result, 'document') and hasattr(result.document, 'title'):
        data['title'] = result.document.title
    else:
        data['title'] = '無標題'
    
    if hasattr(result, 'url'):
        data['url'] = result.url
    elif hasattr(result, 'document') and hasattr(result.document, 'url'):
        data['url'] = result.document.url
    else:
        data['url'] = '#'
    
    if hasattr(result, 'text'):
        data['text'] = result.text
    elif hasattr(result, 'content'):
        data['text'] = result.content
    elif hasattr(result, 'document') and hasattr(result.document, 'text'):
        data['text'] = result.document.text
    else:
        data['text'] = '無內容'
    
    if hasattr(result, 'published_date'):
        data['published_date'] = result.published_date
    elif hasattr(result, 'document') and hasattr(result.document, 'published_date'):
        data['published_date'] = result.document.published_date
    else:
        data['published_date'] = ''
    
    return data

# 從字典中提取數據
def extract_data_from_dict(result_dict):
    """從字典中提取數據"""
    data = {
        'title': result_dict.get('title', '無標題'),
        'url': result_dict.get('url', '#'),
        'text': result_dict.get('text', result_dict.get('content', '無內容')),
        'published_date': result_dict.get('published_date', '')
    }
    
    # 如果有 document 字段，嘗試從中提取數據
    if 'document' in result_dict and isinstance(result_dict['document'], dict):
        doc = result_dict['document']
        if not data['title'] or data['title'] == '無標題':
            data['title'] = doc.get('title', '無標題')
        if not data['url'] or data['url'] == '#':
            data['url'] = doc.get('url', '#')
        if not data['text'] or data['text'] == '無內容':
            data['text'] = doc.get('text', doc.get('content', '無內容'))
        if not data['published_date']:
            data['published_date'] = doc.get('published_date', '')
        
    return data

# 執行 Exa 搜索
def run_exa_search(keyword, start_date, end_date, max_results=100):
    exa = get_exa_client()
    
    try:
        formatted_start = format_date_for_api(start_date)
        formatted_end = format_date_for_api(end_date)
        
        with st.spinner(f"搜索 {start_date.strftime('%Y-%m')} 的資料..."):
            result = exa.search_and_contents(
                keyword,
                # !!!!!
                category="news", # news, tweet, financial report, company
                text={
                    "max_characters": 1000
                },
                type="keyword",
                num_results=max_results,
                start_published_date=formatted_start,
                end_published_date=formatted_end
            )
            
            # 調試信息
            # st.write(f"API 響應類型: {type(result)}")
            
            # 檢查響應結構
            if hasattr(result, 'results'):
                st.write(f"找到 {len(result.results)} 個結果")
                return result
            elif hasattr(result, 'data') and hasattr(result.data, 'results'):
                st.write(f"找到 {len(result.data.results)} 個結果")
                return result.data
            else:
                # 嘗試將結果轉換為字典
                try:
                    if hasattr(result, 'to_dict'):
                        result_dict = result.to_dict()
                        st.write("轉換為字典:", result_dict.keys())
                        
                        if 'data' in result_dict and 'results' in result_dict['data']:
                            class ResultWrapper:
                                def __init__(self, results):
                                    self.results = results
                            
                            return ResultWrapper(result_dict['data']['results'])
                except Exception as e:
                    st.error(f"轉換結果時出錯: {str(e)}")
                
                st.warning(f"API 響應缺少 'results' 屬性。可用屬性: {dir(result)}")
                return None
    except Exception as e:
        st.error(f"搜索時發生錯誤: {str(e)}")
        return None

# 並行執行多個 Exa 搜索
def run_parallel_exa_searches(keyword, month_ranges, max_results_per_month):
    """並行執行多個 Exa 搜索"""
    all_results = []
    total_results = 0
    
    # 創建主頁面容器來顯示進度
    progress_area = st.empty()
    status_area = st.empty()
    
    with progress_area:
        progress_bar = st.progress(0)
    
    # 創建一個執行器
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # 提交所有任務
        future_to_month = {
            executor.submit(run_exa_search, keyword, month['start'], month['end'], max_results_per_month): month
            for month in month_ranges
        }
        
        # 處理完成的任務
        completed = 0
        for future in concurrent.futures.as_completed(future_to_month):
            month = future_to_month[future]
            try:
                result = future.result()
                if result and hasattr(result, 'results'):
                    print('~~~~')
                    print(result)
                    month_results = [extract_data_from_result(r) for r in result.results]
                    all_results.extend(month_results)
                    total_results += len(month_results)
                    with status_area:
                        st.text(f"已完成 {month['name']} 的搜索，找到 {len(month_results)} 個結果")
            except Exception as e:
                with st.container():
                    st.error(f"搜索 {month['name']} 時發生錯誤: {str(e)}")
            
            # 更新進度
            completed += 1
            progress_bar.progress(completed / len(month_ranges))
    
    # 清除進度條和狀態文本
    progress_area.empty()
    status_area.empty()
    
    return all_results, total_results

# 使用 Gemini 分析搜索結果
def analyze_with_gemini(search_results, keyword):
    """使用 Gemini 分析搜索結果並提取重要事件"""
    client = get_gemini_client()
    if not client:
        return None
    
    # 準備輸入數據
    input_text = f"關鍵詞: {keyword}\n\n搜索結果:\n\n"
    
    # 添加每個搜索結果
    for i, result in enumerate(search_results):
        data = extract_data_from_result(result)
        # 格式化日期
        try:
            # 假設日期格式為 YYYY-MM-DD
            if data['published_date'] and len(data['published_date']) >= 10:
                parsed_date = datetime.fromisoformat(data['published_date'].replace('Z', '+00:00'))
                formatted_date = parsed_date.strftime('%Y-%m-%d')
            else:
                formatted_date = data['published_date'] or '未知日期'
        except Exception as e:
            formatted_date = data['published_date'] or '未知日期'
            
        input_text += f"[{i+1}] 標題: {data['title']}\n"
        input_text += f"日期: {formatted_date}\n"
        input_text += f"內容: {data['text'][:1000]}\n\n"
    
    try:
        model = "gemini-2.0-flash"
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=input_text),
                ],
            ),
        ]
        
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type = genai.types.Type.OBJECT,
                properties = {
                    "events": genai.types.Schema(
                        type = genai.types.Type.ARRAY,
                        items = genai.types.Schema(
                            type = genai.types.Type.OBJECT,
                            properties = {
                                "time": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                                "text": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                            },
                        ),
                    ),
                },
            ),
            system_instruction=[
                types.Part.from_text(text="""你是一位資深的投資分析師，統整出各時間點，要跟 {keyword} 有關的事件，請根據新聞資料，篩選出「對投資決策有幫助」的重點資訊。
                判斷新聞是否有幫助包括但不限於：新業務、新產品、新合作、即將推出、出海成功海外爆火、新技術、新產線、產業趨勢、政府政策、重大風險、重大財務異動、重大人事變動、法說會內容、競爭對手訊息、對未來的預測、券商新觀點、券商首次覆蓋
                注意，一定要跟 投資分析有關的事件
                time是發布日期，text是身為分析師應該要提到的重點事件
                text格式為兩段:  重點短語：重點內文 

                text 以SCQA 結構化表達
                S – Situation（情境）
                C – Complication（衝突 / 複雜化）
                Q – Question（問題）
                A – Answer（回答 / 解決方案）

                重點短語 只說 Answer（回答 / 解決方案），有重點數字 或是Action 可以包含在內， 前面加上emoji分別表示 📉📉Strong negative / 📉negative / ⚖️Neutral / 📈positive / 📈📈Strong positive
                重點內文 背後用 SCQ 的結構回答，不過不要特別標記出S:C:Q:，是通順的文字即可

                注意！一定要是 資深的基本面投資分析師 會說的話

                重點短語：重點內文  的範例如下:
                東南亞市場增長 25%：日本市場需求趨緩，東南亞訂單成長成為未來主要營收動能.....

                """),
            ],
        )

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        return response.text
    except Exception as e:
        st.error(f"Gemini 分析時出錯: {str(e)}")
        st.error(f"錯誤類型: {type(e).__name__}")
        import traceback
        st.error(f"詳細錯誤: {traceback.format_exc()}")
        return None

# 主頁面
# st.title("📊 Timeline AI")
# st.subheader("基於關鍵詞的時間線分析")

# 初始化會話狀態
if 'gemini_analysis' not in st.session_state:
    st.session_state.gemini_analysis = None
if 'search_keyword' not in st.session_state:
    st.session_state.search_keyword = ""
if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# 顯示 Gemini 分析結果（如果有）
if st.session_state.gemini_analysis:
    with st.container():
        
        # 使用 Gemini 獲取股票代碼
        def get_stock_ticker_from_gemini(keyword):
            """使用 Gemini 獲取與關鍵詞相關的股票代碼"""
            client = get_gemini_client()
            if not client:
                return None
            
            try:
                model = "gemini-2.0-flash"
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text="""泡泡瑪特"""),
                        ],
                    ),
                    types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(text="""{
  \"events\": \"9992:HKG\"
}"""),
                        ],
                    ),
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=keyword),
                        ],
                    ),
                ]
                
                generate_content_config = types.GenerateContentConfig(
                    temperature=1,
                    top_p=0.95,
                    top_k=40,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    response_schema=genai.types.Schema(
                        type = genai.types.Type.OBJECT,
                        properties = {
                            "ticker": genai.types.Schema(
                                type = genai.types.Type.STRING,
                            ),
                        },
                    ),
                    system_instruction=[
                        types.Part.from_text(text="""找出跟這個最相關的股票代碼，要是tradingview股票代碼格式，像是 TWSE:2412 HKEX:992 HKEX:9992 NASDAQ:AAPL SSE:688256 SZSE:002802"""),
                    ],
                )

                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                )
                
                try:
                    # 解析 JSON 響應
                    ticker_data = json.loads(response.text)
                    if 'ticker' in ticker_data and ticker_data['ticker']:
                        print(ticker_data['ticker'])
                        return ticker_data['ticker']
                except json.JSONDecodeError:
                    st.error(f"無法解析 Gemini 返回的股票代碼: {response.text}")
                    
                return None
            except Exception as e:
                st.error(f"獲取股票代碼時出錯: {str(e)}")
                return None
        
        stock_ticker = get_stock_ticker_from_gemini(st.session_state.search_keyword)
        
        if stock_ticker:
            print(stock_ticker)
            # 添加 TradingView 小工具
            components.html( f"""
            <!-- TradingView Widget BEGIN -->
            <div class="tradingview-widget-container">
              <div id="tradingview_chart"></div>
              <div class="tradingview-widget-copyright"><a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank"><span class="blue-text">Track all markets on TradingView</span></a></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget(
              {{
                "width": "100%",
                "height": 650,
                "symbol": "{stock_ticker}",
                "interval": "D",
                "timezone": "Asia/Taipei",
                "theme": "light",
                "style": "1",
                "locale": "zh_TW",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "container_id": "tradingview_chart"
              }}
              );
              </script>
            </div>
            <!-- TradingView Widget END -->""", height=500)
        

        try:
            # 解析 JSON 韉應
            analysis_data = json.loads(st.session_state.gemini_analysis)
            
            if 'events' in analysis_data and isinstance(analysis_data['events'], list):
                events = analysis_data['events']
                
                # 創建時間線可視化
                timeline_data = []
                
                for event in events:
                    time_str = event.get('time', '未知日期')
                    text = event.get('text', '')
                    
                    # 嘗試解析日期
                    try:
                        # 假設日期格式為 YYYY-MM-DD
                        if len(time_str) >= 10:
                            parsed_date = datetime.fromisoformat(time_str[:10].replace('Z', '+00:00'))
                            formatted_date = parsed_date.strftime('%Y-%m-%d')
                            
                            # 只有有效的日期才添加到時間線
                            timeline_data.append({
                                "id": str(len(timeline_data) + 1),
                                # "content": text[:50] + "..." if len(text) > 50 else text,
                                "content": text,
                                "start": formatted_date
                            })
                    except Exception as e:
                        # 日期格式無效，跳過此事件的時間線
                        pass
                
                # 如果有足夠的事件用於時間線
                if len(timeline_data) >= 2:
                    st.markdown('<div class="timeline-container"><h2 class="timeline-title">📅 事件時間線</h2></div>', unsafe_allow_html=True)
                    
                    # 創建自定義時間線可視化
                    # 按日期排序
                    timeline_data.sort(key=lambda x: x["start"])
                    
                    # 創建時間線
                    st.markdown("""
                    <style>
                    .custom-timeline {
                        position: relative;
                        max-width: 1200px;
                        margin: 0 auto;
                        padding-left: 50px;
                        padding-top: 20px;
                        padding-bottom: 20px;
                    }
                    .custom-timeline::before {
                        content: '';
                        position: absolute;
                        width: 6px;
                        background: linear-gradient(to bottom, #6e8efb, #a777e3);
                        top: 0;
                        bottom: 0;
                        left: 20px;
                        margin-left: -3px;
                        border-radius: 5px;
                    }
                    .timeline-item {
                        padding: 10px 40px;
                        position: relative;
                        background-color: inherit;
                        margin-bottom: 30px;
                    }
                    .timeline-item::before {
                        content: '';
                        position: absolute;
                        width: 24px;
                        height: 24px;
                        background: white;
                        border: 4px solid #6e8efb;
                        top: 15px;
                        border-radius: 50%;
                        z-index: 1;
                        left: -12px;
                        box-shadow: 0 0 0 5px rgba(110, 142, 251, 0.2);
                        transition: all 0.3s ease;
                    }
                    .timeline-item:hover::before {
                        background-color: #6e8efb;
                        box-shadow: 0 0 0 8px rgba(110, 142, 251, 0.3);
                    }
                    .timeline-content {
                        padding: 20px;
                        background-color: white;
                        position: relative;
                        border-radius: 10px;
                        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                        border-left: 5px solid #6e8efb;
                        transition: all 0.3s ease;
                    }
                    .timeline-content:hover {
                        transform: translateY(-5px);
                        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                    }
                    .timeline-date {
                        font-weight: bold;
                        color: #6e8efb;
                        margin-bottom: 10px;
                        font-size: 1.1em;
                        display: flex;
                        align-items: center;
                    }
                    .timeline-date svg {
                        margin-right: 8px;
                    }
                    .timeline-content p {
                        margin: 0;
                        line-height: 1.6;
                        color: #444;
                    }
                    </style>
                    <div class="custom-timeline">
                    """, unsafe_allow_html=True)
                    
                    for item in timeline_data:
                        # 分割內容，使冒號前的文字加粗
                        content = item["content"]
                        if "：" in content:
                            parts = content.split("：", 1)
                            formatted_content = f"<strong>{parts[0]}</strong>：{parts[1]}"
                        else:
                            formatted_content = content
                        
                        st.markdown(f"""
                        <div class="timeline-item">
                            <div class="timeline-content">
                                <div class="timeline-date">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M19 4H5C3.89543 4 3 4.89543 3 6V20C3 21.1046 3.89543 22 5 22H19C20.1046 22 21 21.1046 21 20V6C21 4.89543 20.1046 4 19 4Z" stroke="#6e8efb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        <path d="M16 2V6" stroke="#6e8efb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        <path d="M8 2V6" stroke="#6e8efb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        <path d="M3 10H21" stroke="#6e8efb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                    </svg>
                                    {item["start"]}
                                </div>
                                <p>{formatted_content}</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                
                # 顯示搜索結果
                st.subheader("📋 搜索結果")
                for result in st.session_state.search_results:
                    try:
                        # 格式化日期
                        try:
                            date_obj = datetime.fromisoformat(result['published_date'].replace('Z', '+00:00'))
                            formatted_date = date_obj.strftime('%Y-%m-%d')
                        except:
                            formatted_date = result['published_date']
                        
                        # 使用卡片樣式顯示結果
                        with st.container():
                            st.markdown(f"### {result['title']}")
                            st.markdown(f"**發布日期**: {formatted_date}")
                            st.markdown(f"**URL**: [{result['url']}]({result['url']})")
                            st.markdown(f"**內容**: {result['text']}")
                            st.markdown("---")
                    except Exception as e:
                        st.error(f"處理結果時出錯: {str(e)}")
                        st.write("錯誤類型:", type(e))
                        st.write("原始結果數據:")
                        st.write(result)
            else:
                st.write(st.session_state.gemini_analysis)
        except json.JSONDecodeError:
            # 如果不是 JSON 格式，直接顯示文本
            st.write(st.session_state.gemini_analysis)

# 側邊欄輸入
with st.sidebar:
    st.header("搜索設置")
    
    # 關鍵詞輸入
    search_keyword = st.text_input("輸入搜索關鍵詞", placeholder="例如: 快手kling新聞")
    
    # 日期範圍選擇
    st.subheader("日期範圍")
    default_start, default_end = get_default_dates()
    
    start_year = st.selectbox("開始年份", 
                             options=list(range(2010, datetime.now().year + 1)),
                             index=list(range(2010, datetime.now().year + 1)).index(default_start.year))
    
    start_month = st.selectbox("開始月份", 
                              options=list(range(1, 13)),
                              index=default_start.month - 1)
    
    end_year = st.selectbox("結束年份", 
                           options=list(range(2010, datetime.now().year + 1)),
                           index=list(range(2010, datetime.now().year + 1)).index(default_end.year))
    
    end_month = st.selectbox("結束月份", 
                            options=list(range(1, 13)),
                            index=default_end.month - 1)
    
    # 每月最大結果數
    max_results_per_month = st.slider("每月最大結果數", 10, 100, 100)
    
    # 搜索按鈕
    if st.button("🔍 開始搜索", type="primary", use_container_width=True):
        # 清除先前的結果
        st.session_state.gemini_analysis = None
        st.session_state.search_keyword = ""
        st.session_state.search_results = None
        
        # 驗證輸入
        if not search_keyword:
            st.error("請輸入搜索關鍵詞")
        else:
            # 創建開始和結束日期
            start_date = datetime(start_year, start_month, 1)
            
            # 結束日期設為所選月份的最後一天
            last_day = calendar.monthrange(end_year, end_month)[1]
            end_date = datetime(end_year, end_month, last_day, 23, 59, 59, 999999)
            
            # 檢查日期範圍是否有效
            if start_date > end_date:
                st.error("開始日期不能晚於結束日期")
            else:
                main_area = st.container()
                with main_area:
                    info_msg = st.info(f"正在搜索: {search_keyword} (從 {start_date.strftime('%Y-%m')} 到 {end_date.strftime('%Y-%m')})")
                
                    # 生成月份範圍
                    month_ranges = generate_month_ranges(start_date, end_date)
                
                    # 使用並行搜索替代原來的循環
                    all_results, total_results = run_parallel_exa_searches(keyword=search_keyword, month_ranges=month_ranges, max_results_per_month=max_results_per_month)
                
                    # 顯示總結果數量
                    info_msg.empty()  # 清除搜索信息
                    st.success(f"搜索完成! 總共找到 {total_results} 個結果")
                    
                # 只有在有結果時才進行 Gemini 分析
                if total_results > 0:
                    # Gemini 分析
                    with st.spinner("🤖 Gemini AI 正在分析搜索結果，請稍候..."):
                        gemini_analysis = analyze_with_gemini(all_results, search_keyword)
                        if gemini_analysis:
                            st.session_state.gemini_analysis = gemini_analysis
                            st.session_state.search_keyword = search_keyword
                            st.session_state.search_results = all_results
                            st.rerun()
                    
                else:
                    st.warning("沒有找到任何結果，請嘗試不同的關鍵詞或日期範圍")
