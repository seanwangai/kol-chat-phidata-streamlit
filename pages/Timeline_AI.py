import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import calendar
from collections import Counter
from itertools import cycle
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
    # 使用密钥池轮换机制
    if "exa_api_key_cycle" not in st.session_state:
        st.session_state.exa_api_key_cycle = cycle(st.secrets["EXA_API_KEYS"])
    return Exa(api_key=next(st.session_state.exa_api_key_cycle))

# 設置 Gemini API
def get_gemini_client():
    """獲取 Gemini API 客戶端"""
    # 使用密钥池轮换机制
    if "google_api_key_cycle" not in st.session_state:
        st.session_state.google_api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
    return genai.Client(api_key=next(st.session_state.google_api_key_cycle))

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
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 開始搜索 {start_date.strftime('%Y-%m')} 的資料...")
        with st.spinner(f"搜索 {start_date.strftime('%Y-%m')} 的資料..."):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在調用 Exa API...")
            result = exa.search_and_contents(
                keyword,
                category="news",
                text={
                    "max_characters": 1000
                },
                type="keyword",
                num_results=max_results,
                start_published_date=formatted_start,
                end_published_date=formatted_end,
                exclude_domains = ["keji100.net"]
            )
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Exa API 調用完成，正在處理結果...")
            
            if hasattr(result, 'results'):
                result_count = len(result.results)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 找到 {result_count} 個結果")
                st.write(f"找到 {result_count} 個結果")
                return result
            elif hasattr(result, 'data') and hasattr(result.data, 'results'):
                result_count = len(result.data.results)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 找到 {result_count} 個結果")
                st.write(f"找到 {result_count} 個結果")
                return result.data
            else:
                try:
                    if hasattr(result, 'to_dict'):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在轉換結果格式...")
                        result_dict = result.to_dict()
                        st.write("轉換為字典:", result_dict.keys())
                        
                        if 'data' in result_dict and 'results' in result_dict['data']:
                            class ResultWrapper:
                                def __init__(self, results):
                                    self.results = results
                            
                            result_count = len(result_dict['data']['results'])
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 找到 {result_count} 個結果")
                            return ResultWrapper(result_dict['data']['results'])
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 轉換結果時出錯: {str(e)}")
                    st.error(f"轉換結果時出錯: {str(e)}")
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] API 響應格式異常")
                st.warning(f"API 響應缺少 'results' 屬性。可用屬性: {dir(result)}")
                return None
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 搜索出錯: {str(e)}")
        st.error(f"搜索時發生錯誤: {str(e)}")
        return None

# 並行執行多個 Exa 搜索
def run_parallel_exa_searches(keyword, month_ranges, max_results_per_month):
    """並行執行多個 Exa 搜索"""
    all_results = []
    total_results = 0
    
    # 創建主頁面容器來顯示進度
    progress_container = st.container()
    status_area = st.empty()
    
    with progress_container:
        progress_bar = st.progress(0)
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 開始並行搜索，共 {len(month_ranges)} 個月份")
    
    # 創建一個執行器
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        # 提交所有任務
        future_to_month = {
            executor.submit(run_exa_search, keyword, month['start'], month['end'], max_results_per_month): month
            for month in month_ranges
        }
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 已提交所有搜索任務")
        
        # 處理完成的任務
        completed = 0
        for future in concurrent.futures.as_completed(future_to_month):
            month = future_to_month[future]
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在處理 {month['name']} 的搜索結果...")
                result = future.result()
                if result and hasattr(result, 'results'):
                    month_results = [extract_data_from_result(r) for r in result.results]
                    all_results.extend(month_results)
                    total_results += len(month_results)
                    with status_area:
                        st.text(f"已完成 {month['name']} 的搜索，找到 {len(month_results)} 個結果")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {month['name']} 處理完成，找到 {len(month_results)} 個結果")
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {month['name']} 處理出錯: {str(e)}")
                with st.container():
                    st.error(f"搜索 {month['name']} 時發生錯誤: {str(e)}")
            
            # 更新進度
            completed += 1
            progress = completed / len(month_ranges)
            progress_bar.progress(progress)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 總進度: {progress*100:.1f}%")
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 所有搜索任務完成，共找到 {total_results} 個結果")
    
    # 清除進度條和狀態文本
    progress_container.empty()
    status_area.empty()
    
    # 按日期排序結果
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在對結果進行排序...")
    sorted_results = sorted(all_results, 
                          key=lambda x: datetime.fromisoformat(x['published_date'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc) if x['published_date'] else datetime.min.replace(tzinfo=timezone.utc),
                          reverse=True)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 排序完成")
    
    return sorted_results, total_results

# 使用 Gemini 分析搜索结果
def analyze_with_gemini(search_results, keyword):
    """使用 Gemini 分析搜索结果并提取重要事件"""
    # 按月份分組结果
    results_by_month = {}
    for result in search_results:
        try:
            date_obj = datetime.fromisoformat(result['published_date'].replace('Z', '+00:00'))
            month_key = date_obj.strftime('%Y-%m')
            
            if month_key not in results_by_month:
                results_by_month[month_key] = []
            
            results_by_month[month_key].append(result)
        except Exception as e:
            # !!!!!! 有些publish_date 是none
            # TO FIX: 如果是 published_date 是 None ，date 改用end_published_date=formatted_end,
            print(f"处理日期时出错: {str(e)}")
            print(result)
    
    # 创建进度显示（在主页而非侧边栏）
    analysis_container = st.container()
    with analysis_container:
        analysis_progress = st.progress(0)
        analysis_status = st.empty()
    
    # 存储所有月份的进行分析结果
    all_events = []
    
    def analyze_month_data(month_data):
        month, month_results = month_data
        try:
            # 准备输入文本
            input_text = f"以下是关于 '{keyword}' 在 {month} 的新闻报导，请分析并提取重要事件：\n\n"
            
            # 添加每个结果的数据
            for j, data in enumerate(month_results):
                try:
                    date_obj = datetime.fromisoformat(data['published_date'].replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                except:
                    formatted_date = data['published_date']
                
                input_text += f"[{j+1}] 标题: {data['title']}\n"
                input_text += f"日期: {formatted_date}\n"
                input_text += f"内容: {data['text'][:1000]}\n\n"
            
            # 获取新的 client 并分析
            client = get_gemini_client()
            month_analysis = call_gemini_api(client, input_text, keyword)
            
            # 解析 JSON 响应
            try:
                month_events = json.loads(month_analysis)
                if 'events' in month_events and isinstance(month_events['events'], list):
                    return month_events['events']
            except json.JSONDecodeError:
                print(f"无法解析 {month} 的 Gemini 分析结果")
                print(month_analysis)
                return []
        except Exception as e:
            print(f"分析 {month} 数据时出错: {str(e)}")
            return []
    
    # 使用线程池并行处理
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # 提交所有任务
        future_to_month = {executor.submit(analyze_month_data, (month, results)): month 
                         for month, results in results_by_month.items()}
        
        # 处理完成的任务
        completed = 0
        for future in concurrent.futures.as_completed(future_to_month):
            month = future_to_month[future]
            try:
                month_events = future.result()
                all_events.extend(month_events)
            except Exception as e:
                st.error(f"处理 {month} 数据时出错: {str(e)}")
            
            # 更新进度
            completed += 1
            progress_value = min(1.0, max(0.0, completed / len(results_by_month)))
            analysis_progress.progress(progress_value)
            analysis_status.text(f"已完成 {completed}/{len(results_by_month)} 个月份的分析...")
    
    # 清除进度显示
    analysis_progress.empty()
    analysis_status.empty()
    
    # 返回合併的分析结果
    combined_analysis = {
        "events": all_events
    }
    
    return json.dumps(combined_analysis)

# 調用 Gemini API
def call_gemini_api(client, input_text, keyword):
    """調用 Gemini API 進行分析"""
    max_retries = 3
    timeout_seconds = 15
    
    for retry_count in range(max_retries):
        try:
            model = "gemini-2.0-flash"
            
            # 設置系統指令  
            system_instruction = f"""**角色設定：**  
            你是一位資深的基本面投資分析師，負責整理各時間點與 {keyword} 有關的新聞資料，挑選「對投資決策有幫助」的重大事件。

            ---

            ### ✅ 任務目標：  
            依據新聞內容，篩選出對基本面分析有價值的資訊，統整出時間序列資訊表，重點聚焦在影響公司營運、財報、產業地位與未來發展的資訊。  
            **排除所有股價漲跌相關資訊**，專注於事件對基本面的影響。
            注意，一定要跟 {keyword} 有關，無關的新聞，請直接略過。
            如果相近的天數，有兩個一樣的新聞，請選擇發生時間最早的新聞，整在一起即可。

            ---

            ### ✅ 新聞判斷標準（符合下列條件的新聞才需整理）：  
            - 新業務 / 新產品 / 新合作 / 即將推出  
            - 出海成功 / 海外市場增長 / 海外熱銷  
            - 新技術 / 新產線 / 技術突破  
            - 產業趨勢 / 政策導向 / 法規影響  
            - 政府政策支持 / 補貼  
            - 重大風險 / 法律糾紛 / 營運風險  
            - 重大財務異動（營收、獲利、毛利等）  
            - 重大人事異動（高階主管更換）  
            - 法說會 / 財報重點 / 公司展望  
            - 券商觀點 / 首次覆蓋 / 調升調降目標  
            - 競爭對手重大動作（新產品、新產線、重大合作等）

            ---

            ### ✅ 輸出格式（務必遵守）：  
            以時間為排序單位，呈現重要新聞資訊，格式如下：

            ```
            time: YYYY-MM-DD  
            text:  
            {{emoji}}{{重點短語}}：  
            {{SCQA 結構重點內文}}
            ```

            ---

            ### ✅ SCQA 結構說明  
            - **S（Situation）**：描述當前的背景或產業/公司現況  
            - **C（Complication）**：指出面臨的變化、挑戰或潛在機會  
            - **Q（Question）**：提出市場或投資人關注的問題  
            - **A（Answer）**：公司或產業的應對措施、具體行動或預期結果（這部分需寫在重點短語前）

            ---

            ### ✅ 重點短語規則  
            - 前面加上 sentiment emoji  
                - 📈📈 Strong positive  
                - 📈 Positive  
                - ⚖️ Neutral  
                - 📉 Negative  
                - 📉📉 Strong negative  
            重點短語只寫 Answer（具體作為/數字/結論）  
            簡明扼要，清楚展示影響力（新訂單、新市場、營收變化等）  

            ---

            ### ✅ 範例  
            ```
            time: 2025-03-18  
            text:  
            📈📈 東南亞市場訂單成長 25%：  
            日本市場需求趨緩，導致公司在亞洲區域營收承壓。為突破瓶頸，公司積極拓展東南亞市場。  
            東南亞經濟復甦帶動整體需求上升，市場對公司主力產品需求大幅增長。  
            投資人關注公司是否能成功彌補日本市場下滑的缺口。  
            最新數據顯示，公司東南亞市場訂單季增 25%，有望成為未來主要營收動能來源。

            time: 2025-03-12  
            text:  
            📉📉 核心技術專利糾紛導致產品延遲上市：  
            公司計畫在上半年推出新一代旗艦產品，以鞏固高端市場地位。然而，因涉及專利侵權，公司被競爭對手提起訴訟。  
            市場普遍擔心訴訟將影響產品上市時程及市場信心。  
            目前，公司已宣布產品上市將延遲兩個季度，恐影響下半年營收表現。
            ```
            
            ### text 錯誤範例： 
            - 📈 快手电商双11战报： S：快手电商发布双11购物节收官战报。 C：市场关注快手电商双11的业绩。 Q：快手电商双11的整体表现如何？ A：快手电商泛货架商品卡GMV同比增长110%，搜索GMV同比增长119%。
            是錯誤的，因為出現了 S： C： Q： A： ，這是嚴格禁止的
            正確應該是
            - 📈 快手电商双11战报： 快手电商发布双11购物节收官战报。市场关注快手电商双11的业绩。快手电商双11的整体表现如何？快手电商泛货架商品卡GMV同比增长110%，搜索GMV同比增长119%。
            ---

            ### ✅ 小技巧提醒  
            - 重點不在「新聞」，而在「對營運基本面的影響」。  
            - 不重要的、冗餘的資訊要學會「刪減」或「合併」。  
            - emoji 決定這條資訊的投資情緒。  
            - 模型輸出只關注 **有用的事實**，而非新聞表象。
            """


            # 組合提示詞
            prompt = f"{system_instruction}\n\n{input_text}"
            
            # 設置 Gemini 請求
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.95,
                top_k=40,
                max_output_tokens=50000,
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
            )
            
            # 使用 timeout 發送請求
            # 使用 concurrent.futures 實現 timeout
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    client.models.generate_content,
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                )
                
                try:
                    response = future.result(timeout=timeout_seconds)
                    # 返回響應文本
                    return response.text
                except concurrent.futures.TimeoutError:
                    if retry_count < max_retries - 1:
                        st.warning(f"Gemini API 請求超時，正在重試 ({retry_count + 1}/{max_retries})...")
                        continue
                    else:
                        raise TimeoutError(f"Gemini API 請求在 {timeout_seconds} 秒內未完成，已重試 {max_retries} 次")
                
        except TimeoutError as e:
            st.error(f"調用 Gemini API 時出錯: {str(e)}")
            return json.dumps({"events": []})
        except Exception as e:
            if retry_count < max_retries - 1:
                st.warning(f"Gemini API 請求出錯，正在重試 ({retry_count + 1}/{max_retries}): {str(e)}")
                continue
            else:
                st.error(f"調用 Gemini API 時出錯: {str(e)}")
                return json.dumps({"events": []})
    
    # 如果所有重試都失敗
    return json.dumps({"events": []})

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
                    max_output_tokens=50000,
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
                        ticker = ticker_data['ticker']
                        print(ticker)
                        
                        # 檢查是否為 HKEX 或 TWSE
                        if ticker.startswith(('HKEX:', 'TWSE:')):
                            # 生成 TradingView 鏈接
                            tradingview_symbol = ticker.replace(':', '%3A')
                            tradingview_url = f"https://www.tradingview.com/chart?symbol={tradingview_symbol}"
                            
                            # 顯示 TradingView 鏈接
                            st.markdown(f"[在 TradingView 中查看 {ticker}]({tradingview_url})")
                        
                        return ticker
                except json.JSONDecodeError:
                    st.error(f"無法解析 Gemini 返回的股票代碼: {response.text}")
                    
                return None
            except Exception as e:
                # st.error(f"獲取股票代碼時出錯: {str(e)}")
                print(f"獲取股票代碼時出錯: {str(e)}")
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
                "height": 600,
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
            <!-- TradingView Widget END -->""", height=600)
        

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
                    st.markdown('<div class="timeline-container"><h2 class="timeline-title">📅 事件時間線 <span class="copy-icon" onclick="copyTimelineEvents()" title="複製時間線內容"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M20 9H11C9.89543 9 9 9.89543 9 11V20C9 21.1046 9.89543 22 11 22H20C21.1046 22 22 21.1046 22 20V11C22 9.89543 21.1046 9 20 9Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 15H4C3.46957 15 2.96086 14.7893 2.58579 14.4142C2.21071 14.0391 2 13.5304 2 13V4C2 3.46957 2.21071 2.96086 2.58579 2.58579C2.96086 2.21071 3.46957 2 4 2H13C13.5304 2 14.0391 2.21071 14.4142 2.58579C14.7893 2.96086 15 3.46957 15 4V5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span></h2></div>', unsafe_allow_html=True)
                    
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
                        padding: 5px 40px;
                        position: relative;
                        background-color: inherit;
                        margin-bottom: 15px;
                    }
                    .timeline-item::before {
                        content: '';
                        position: absolute;
                        width: 24px;
                        height: 24px;
                        background: white;
                        border: 4px solid var(--circle-color, #6e8efb);
                        top: 15px;
                        border-radius: 50%;
                        z-index: 1;
                        left: -12px;
                        box-shadow: 0 0 0 5px var(--circle-shadow-color, rgba(110, 142, 251, 0.2));
                        transition: all 0.3s ease;
                    }
                    .timeline-item[data-sentiment='📈']::before, .timeline-item[data-sentiment='📈📈']::before {
                        border-color: #ff6b6b;
                        box-shadow: 0 0 0 5px rgba(255, 107, 107, 0.2);
                    }
                    .timeline-item[data-sentiment='⚖️']::before {
                        border-color: #868e96;
                        box-shadow: 0 0 0 5px rgba(134, 142, 150, 0.2);
                    }
                    .timeline-item[data-sentiment='📉']::before, .timeline-item[data-sentiment='📉📉']::before {
                        border-color: #51cf66;
                        box-shadow: 0 0 0 5px rgba(81, 207, 102, 0.2);
                    }
                    .timeline-item:hover::before {
                        background-color: var(--circle-color, #6e8efb);
                        box-shadow: 0 0 0 8px var(--circle-shadow-color, rgba(110, 142, 251, 0.3));
                    }
                    .timeline-item[data-sentiment='📈']:hover::before, .timeline-item[data-sentiment='📈📈']:hover::before {
                        background-color: #ff6b6b;
                        box-shadow: 0 0 0 8px rgba(255, 107, 107, 0.3);
                    }
                    .timeline-item[data-sentiment='⚖️']:hover::before {
                        background-color: #868e96;
                        box-shadow: 0 0 0 8px rgba(134, 142, 150, 0.3);
                    }
                    .timeline-item[data-sentiment='📉']:hover::before, .timeline-item[data-sentiment='📉📉']:hover::before {
                        background-color: #51cf66;
                        box-shadow: 0 0 0 8px rgba(81, 207, 102, 0.3)
                    }
                    .timeline-content {
                        padding: 20px;
                        background-color: white;
                        position: relative;
                        border-radius: 10px;
                        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                        transition: all 0.3s ease;
                    }
                    .timeline-content[data-sentiment='📈'], .timeline-content[data-sentiment='📈📈'] {
                        border-left: 5px solid #ff6b6b;
                        background-color: rgba(255, 107, 107, 0.05);
                        --circle-color: #ff6b6b;
                        --circle-shadow-color: rgba(255, 107, 107, 0.2);
                    }
                    .timeline-content[data-sentiment='⚖️'] {
                        border-left: 5px solid #868e96;
                        background-color: rgba(134, 142, 150, 0.05);
                        --circle-color: #868e96;
                        --circle-shadow-color: rgba(134, 142, 150, 0.2);
                    }
                    .timeline-content[data-sentiment='📉'], .timeline-content[data-sentiment='📉📉'] {
                        border-left: 5px solid #51cf66;
                        background-color: rgba(81, 207, 102, 0.05);
                        --circle-color: #51cf66;
                        --circle-shadow-color: rgba(81, 207, 102, 0.2);
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
                    .copy-icon {
                        cursor: pointer;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        margin-left: 10px;
                        padding: 5px;
                        border-radius: 50%;
                        transition: all 0.2s ease;
                        color: #6e8efb;
                    }
                    .copy-icon:hover {
                        background-color: rgba(110, 142, 251, 0.1);
                        transform: scale(1.1);
                    }
                    .copy-icon:active {
                        transform: scale(0.95);
                    }
                    </style>
                    <div class="custom-timeline">
                    """, unsafe_allow_html=True)
                    
                    # 添加JavaScript函數
                    st.markdown("""
                    <script>
                    function scrollToDate(date) {
                        const targetElement = document.getElementById('date-' + date);
                        if (targetElement) {
                            const offset = 80;
                            const elementPosition = targetElement.getBoundingClientRect().top;
                            const offsetPosition = elementPosition - offset;
                            window.scrollBy({
                                top: offsetPosition,
                                behavior: 'smooth'
                            });
                        }
                    }
                    
                    function copyTimelineEvents() {
                        // 收集所有时间线事件
                        const timelineItems = document.querySelectorAll('.timeline-item');
                        let copyText = "📅 事件時間線\n\n";
                        
                        timelineItems.forEach(item => {
                            const dateElement = item.querySelector('.timeline-date');
                            const contentElement = item.querySelector('p');
                            
                            if (dateElement && contentElement) {
                                // 获取日期文本（移除SVG图标）
                                const dateText = dateElement.textContent.trim();
                                // 获取内容文本
                                const contentText = contentElement.textContent.trim();
                                
                                copyText += `${dateText}: ${contentText}\n\n`;
                            }
                        });
                        
                        // 复制到剪贴板
                        navigator.clipboard.writeText(copyText)
                            .then(() => {
                                // 显示复制成功提示
                                const copyIcon = document.querySelector('.copy-icon');
                                const originalTitle = copyIcon.getAttribute('title');
                                copyIcon.setAttribute('title', '複製成功！');
                                copyIcon.style.color = '#51cf66';
                                
                                // 2秒后恢复原样
                                setTimeout(() => {
                                    copyIcon.setAttribute('title', originalTitle);
                                    copyIcon.style.color = '#6e8efb';
                                }, 2000);
                            })
                            .catch(err => {
                                console.error('複製失敗:', err);
                                alert('複製失敗，請重試');
                            });
                    }
                    </script>
                    """, unsafe_allow_html=True)
                    
                    for item in timeline_data:
                        # 分割內容，使冒號前的文字加粗
                        content = item["content"]
                        if "：" in content:
                            parts = content.split("：", 1)
                            formatted_content = f"<strong>{parts[0]}</strong>：{parts[1]}"
                        else:
                            formatted_content = content
                        
                        # 获取情感标记
                        sentiment = '⚖️'  # 默认为中性
                        if "：" in content:
                            first_part = content.split("：")[0]
                            if "📈" in first_part:
                                sentiment = '📈'
                            elif "📉" in first_part:
                                sentiment = '📉'
                            elif "⚖️" in first_part:
                                sentiment = '⚖️'
                        
                        st.markdown(f"""
                        <div class="timeline-item" onclick="scrollToDate('{item['start']}')" style="cursor: pointer;" data-sentiment='{sentiment}'>
                            <div class="timeline-content" data-sentiment='{sentiment}'>
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
                        
                        # 使用卡片樣式顯示結果，添加日期ID作為錨點
                        with st.container():
                            st.markdown(f"<div id='date-{formatted_date}'></div>", unsafe_allow_html=True)
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
                # 清空主頁面
                st.empty()
                
                # 在主頁面顯示搜索進度
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
                    with main_area:
                        with st.spinner("🤖 Gemini AI 正在分析搜索結果，請稍候..."):
                            gemini_analysis = analyze_with_gemini(all_results, search_keyword)
                            if gemini_analysis:
                                st.session_state.gemini_analysis = gemini_analysis
                                st.session_state.search_keyword = search_keyword
                                st.session_state.search_results = all_results
                                st.rerun()
                    
                else:
                    with main_area:
                        st.warning("沒有找到任何結果，請嘗試不同的關鍵詞或日期範圍")
