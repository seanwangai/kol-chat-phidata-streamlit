import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import calendar
from collections import Counter
from itertools import cycle
import json
import time
import os
import re
import zipfile
from dateutil.relativedelta import relativedelta
from exa_py import Exa
from google import genai
from pathlib import Path
import concurrent.futures
import random
import backoff
import httpx

# 页面配置
st.set_page_config(
    page_title="Risk Scanner",
    page_icon="🔍",
    layout="wide"
)

# 初始化会话状态
if "selected_experts" not in st.session_state:
    st.session_state.selected_experts = []
if "expert_agents" not in st.session_state:
    st.session_state.expert_agents = {}
if "should_run_analysis" not in st.session_state:
    st.session_state.should_run_analysis = False
if "expert_names" not in st.session_state:
    st.session_state.expert_names = []
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = {}
if "company_name" not in st.session_state:
    st.session_state.company_name = ""
if "show_search_results" not in st.session_state:
    st.session_state.show_search_results = False
if "selected_model" not in st.session_state:
    st.session_state.selected_model = "gemini-2.5-flash"

# 设置默认选中的专家
DEFAULT_EXPERTS = [
    # "Bonitas Research",
    "Grizzly Research",
    # "Publication - The Most Dangerous Trade",
    # "Hindenburg Research",
    # "Viceroy Research",
    "Muddy Waters",
    # "Publication - Confidence Game",
    # "J Capital"
    "Publication - Financial Shenanigans",
]

# 初始化API客户端
@st.cache_resource
def get_exa_client():
    """获取Exa API客户端并轮换API密钥"""
    if "exa_api_key_cycle" not in st.session_state:
        st.session_state.exa_api_key_cycle = cycle(st.secrets["EXA_API_KEYS"])
    return Exa(api_key=next(st.session_state.exa_api_key_cycle))

@st.cache_resource
def get_gemini_client():
    """获取Gemini API客户端并轮换API密钥"""
    if "google_api_key_cycle" not in st.session_state:
        st.session_state.google_api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
    return genai.Client(api_key=next(st.session_state.google_api_key_cycle))

# 格式化日期为API所需的ISO 8601格式
def format_date_for_api(date):
    """转换为UTC时间格式"""
    return date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# 生成从2020年至今的季度时间范围
def generate_quarter_ranges():
    """生成从2020年至今的季度时间范围"""
    quarters = []
    
    # 起始日期：2020年1月1日
    start_date = datetime(2024, 1, 1)
    # 结束日期：当前日期
    end_date = datetime.now()
    
    current_date = start_date
    while current_date < end_date:
        # 计算当前季度的结束日期
        if current_date.month in [1, 2, 3]:
            quarter_end = datetime(current_date.year, 3, 31, 23, 59, 59, 999999)
        elif current_date.month in [4, 5, 6]:
            quarter_end = datetime(current_date.year, 6, 30, 23, 59, 59, 999999)
        elif current_date.month in [7, 8, 9]:
            quarter_end = datetime(current_date.year, 9, 30, 23, 59, 59, 999999)
        else:
            quarter_end = datetime(current_date.year, 12, 31, 23, 59, 59, 999999)
        
        # 如果季度结束日期超过了当前日期，使用当前日期作为结束
        if quarter_end > end_date:
            quarter_end = end_date
            
        quarters.append({
            'start': current_date,
            'end': quarter_end,
            'name': f"{current_date.year}Q{(current_date.month-1)//3+1}"
        })
        
        # 移动到下一个季度的第一天
        current_date = (quarter_end + timedelta(days=1))
        
    return quarters

# 使用Exa搜索关键词并直接获取内容
def run_exa_search(keyword, start_date, end_date, max_results=100):
    """使用Exa API搜索特定时间范围内的关键词并获取内容"""
    exa = get_exa_client()
    
    try:
        formatted_start = format_date_for_api(start_date)
        formatted_end = format_date_for_api(end_date)
        
        # 移除spinner，因为会在并发搜索中集中显示
        print(f"搜索: {keyword} - {formatted_start} 至 {formatted_end}")
        
        result = exa.search_and_contents(
            keyword,
            type="keyword",
            num_results=max_results,
            start_published_date=formatted_start,
            end_published_date=formatted_end,
            # include_domains=["xueqiu.com"],
            text={
                "max_characters": 10000  # 获取更多内容
            }
        )
        
        # 处理结果并提取内容
        search_results = []
        contents = []
        
        # 直接访问results属性
        if hasattr(result, 'results'):
            search_results = result.results
        # 尝试通过data属性访问
        elif hasattr(result, 'data') and hasattr(result.data, 'results'):
            search_results = result.data.results
        # 尝试转换为字典
        elif hasattr(result, 'to_dict'):
            result_dict = result.to_dict()
            if 'data' in result_dict and 'results' in result_dict['data']:
                search_results = result_dict['data']['results']
        # 处理字典类型
        elif isinstance(result, dict):
            if 'data' in result and 'results' in result['data']:
                search_results = result['data']['results']
            elif 'results' in result:
                search_results = result['results']
        
        # 从结果中提取内容
        for item in search_results:
            content = None
            url = None
            
            # 尝试获取内容
            if hasattr(item, 'text') and item.text:
                content = item.text
            elif isinstance(item, dict) and 'text' in item and item['text']:
                content = item['text']
            
            # 尝试获取URL
            if hasattr(item, 'url'):
                url = item.url
            elif isinstance(item, dict) and 'url' in item:
                url = item['url']
            
            # 添加到结果中
            if content and url:
                contents.append({
                    'url': url,
                    'content': content
                })
        
        return {
            'keyword': keyword,
            'quarter': f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
            'results': search_results,
            'contents': contents
        }
            
    except Exception as e:
        st.error(f"搜索 {keyword} 时出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc(), language="python")
        return {
            'keyword': keyword,
            'quarter': f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}",
            'results': [],
            'contents': []
        }

# 获取专家目录列表
def get_expert_names():
    """获取可用的专家名称列表"""
    expert_dir = Path("data_short_expert")
    
    if not expert_dir.exists():
        st.warning("专家数据目录不存在，尝试下载...")
        if not initialize_dropbox():
            st.error("无法初始化专家数据")
            return []
    
    # 查找所有子目录
    experts = []
    for folder in expert_dir.iterdir():
        if folder.is_dir():
            experts.append(folder.name)
    
    return experts

# 从Dropbox下载专家数据
def initialize_dropbox():
    """初始化Dropbox并下载专家数据"""
    dropbox_url_key = "DROPBOX_DATA_URL_SHORT_EXPERT"
    target_dir = Path("data_short_expert")
    
    if dropbox_url_key in st.secrets:
        try:
            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 修改URL为直接下载链接
            url = st.secrets[dropbox_url_key]
            url = url.split('&dl=')[0] + '&dl=1'
            
            # 确保临时文件路径存在
            temp_zip = target_dir / "temp_download.zip"
            
            try:
                # 下载文件
                import requests
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry
                
                # 设置重试策略
                session = requests.Session()
                retries = Retry(
                    total=5,  # 最多重试5次
                    backoff_factor=1,  # 重试间隔时间
                    status_forcelist=[429, 500, 502, 503, 504],  # 服务器错误时重试
                )
                session.mount('https://', HTTPAdapter(max_retries=retries))
                
                with st.spinner("正在下载专家数据..."):
                    # st.info(f"开始下载: {url}")
                    
                    # 分块下载以便显示进度
                    response = session.get(url, stream=True)
                    response.raise_for_status()
                    
                    # 获取文件大小(字节)
                    total_size = int(response.headers.get('content-length', 0))
                    # st.info(f"文件大小: {total_size/1024/1024:.2f} MB")
                    
                    # 创建进度条
                    progress_bar = st.progress(0)
                    download_status = st.empty()
                    
                    # 写入临时文件
                    downloaded_size = 0
                    chunk_size = 1024 * 1024  # 1MB 块大小
                    
                    try:
                        with open(temp_zip, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    
                                    # 更新进度
                                    if total_size > 0:
                                        progress = min(downloaded_size / total_size, 1.0)
                                        progress_bar.progress(progress)
                                        download_status.write(f"下载进度: {downloaded_size/1024/1024:.2f} MB / {total_size/1024/1024:.2f} MB")
                    except Exception as e:
                        st.error(f"下载过程中断: {str(e)}")
                        if temp_zip.exists():
                            temp_zip.unlink()  # 移除不完整文件
                        raise
                    
                    download_status.empty()
                    progress_bar.empty()
                    
                    st.success(f"下载完成: {temp_zip.stat().st_size/1024/1024:.2f} MB")
                
                # 验证文件
                if not temp_zip.exists():
                    raise FileNotFoundError(f"下载的文件未找到: {temp_zip}")
                
                if not zipfile.is_zipfile(temp_zip):
                    raise ValueError(f"下载的文件不是有效的ZIP文件: {temp_zip}")
                
                # 清空目标目录
                for item in target_dir.iterdir():
                    if item != temp_zip:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            import shutil
                            shutil.rmtree(item)
                
                # 解压文件
                with st.spinner("正在解压专家数据..."):
                    extract_status = st.empty()
                    extract_status.info("开始解压文件...")
                    
                    try:
                        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                            # 获取压缩包中的文件列表
                            file_list = zip_ref.namelist()
                            total_files = len(file_list)
                            
                            # 创建进度条
                            extract_progress = st.progress(0)
                            
                            # 逐个解压文件并更新进度
                            for i, file in enumerate(file_list):
                                extract_status.write(f"解压文件 ({i+1}/{total_files}): {file}")
                                zip_ref.extract(file, target_dir)
                                extract_progress.progress((i+1)/total_files)
                                
                            extract_status.success("解压完成")
                            extract_progress.empty()
                    except Exception as e:
                        extract_status.error(f"解压失败: {str(e)}")
                        raise
                
                # 删除临时ZIP文件
                temp_zip.unlink()
                
                # 更新专家列表
                expert_count = len([f for f in target_dir.iterdir() if f.is_dir()])
                st.success(f"发现 {expert_count} 个专家目录")
                st.session_state.expert_names = get_expert_names()
                
                return True
                
            except Exception as e:
                st.error(f"处理文件时出错: {str(e)}")
                import traceback
                st.code(traceback.format_exc(), language="python")
                return False
                
        except Exception as e:
            st.error(f"初始化失败: {str(e)}")
            return False
            
    st.warning(f"未找到 {dropbox_url_key} 配置信息")
    return False

# 获取专家的头像
def get_expert_avatar(expert_name):
    """根据专家名称获取头像"""
    # 为每个专家配置不同的头像
    avatars = {
        "Bonitas Research": "🔍",
        "Grizzly Research": "🐻",
        "Hindenburg Research": "🔥",
        "Muddy Waters": "🦏",
        "J Capital": "💸",
        "Viceroy Research": "🕵️‍♂️",
        "Citron": "🍋",
        "Spruce": "🌲",
        "Chanos": "🏛️",
        "Publication - Confidence Game": "📚",
        "Publication - The Art of Short Selling": "📖",
        "Publication - The Most Dangerous Trade": "📊",
        "Publication - The Smartest Guys in the Room": "🧩",
        "Publication - Financial Shenanigans": "🎭",
        "Publication - Others": "📝"
    }
    
    # 如果找不到预定义的头像，随机分配一个
    if expert_name not in avatars:
        import random
        random_emojis = ["⚡", "🔬", "📈", "🔮", "🧮", "💼", "🗂️", "📊", "💰", "💹"]
        # 使用专家名称的哈希值来确保同一专家每次获得相同的emoji
        random.seed(hash(expert_name))
        return random.choice(random_emojis)
        
    return avatars.get(expert_name)

# 添加token计数辅助函数
def estimate_tokens(text):
    """估算文本的token数量（粗略估计，使用简单公式）"""
    # 一个简单的估计方法：按空格分词后的词数 * 1.3
    words = text.split()
    return int(len(words) * 1.3)

# 为单个专家创建LLM
def create_expert_llm(expert_name):
    """为单个专家创建LLM"""
    # 检查是否已经创建过模型
    if expert_name in st.session_state.expert_agents:
        return st.session_state.expert_agents[expert_name]
    
    expert_dir = Path("data_short_expert") / expert_name
    expert_knowledge = []
    documents_count = 0
    
    # 读取专家文档内容
    for file in expert_dir.glob("**/*"):
        if file.is_file():
            if file.suffix.lower() in ['.txt', '.md']:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        expert_knowledge.append(f.read())
                        documents_count += 1
                except:
                    pass
            elif file.suffix.lower() == '.pdf':
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file)
                    pdf_text = ""
                    for page in doc:
                        pdf_text += page.get_text()
                    expert_knowledge.append(pdf_text)
                    documents_count += 1
                except:
                    pass
            elif file.suffix.lower() == '.docx':
                try:
                    import docx
                    doc = docx.Document(file)
                    docx_text = ""
                    for para in doc.paragraphs:
                        docx_text += para.text + "\n"
                    expert_knowledge.append(docx_text)
                    documents_count += 1
                except Exception as e:
                    print(f"无法读取docx文件 {file}: {str(e)}")
                    pass
            elif file.suffix.lower() == '.epub':
                try:
                    import ebooklib
                    from ebooklib import epub
                    from bs4 import BeautifulSoup
                    
                    book = epub.read_epub(file)
                    epub_text = ""
                    
                    for item in book.get_items():
                        if item.get_type() == ebooklib.ITEM_DOCUMENT:
                            soup = BeautifulSoup(item.get_content(), 'html.parser')
                            epub_text += soup.get_text() + "\n"
                    
                    expert_knowledge.append(epub_text)
                    documents_count += 1
                except:
                    pass
    
    # 创建专家LLM
    if expert_knowledge:
        # 短一點
        all_expert_knowledge  = ' '.join(expert_knowledge)
        original_length = len(all_expert_knowledge)
        
        
        expert_prompt = f"""你是知名做空機構分析師 以下是你过去short过的所有case
        {all_expert_knowledge} 

========
以上是你过去short过的所有case，我接下來會輸入我在研究的新的公司的資訊，幫我判斷 

1. 根據 你的知識 和你過去經驗 ，分析這家公司 有風險 的可能性多高(高 中 低)？
2. 根據你的知識和過去經驗，有沒有看到這家公司有存在 跟你之前看的case类似的 有造假的 或是有大問題 "危险信号" ，詳細說明，先說這家公司也有的部分，再說這家公司跟 之前看short過的case short主因相似處 詳述之前的case怎樣造假 要非常詳細說明跟過去相似的點
3. 最後根據過去看造假公司的經驗，然後結合這家公司的目前得到的資訊  跟我說可以再深入朝什麼方向研究 做什麼調研 為什麼要作這個調研 

用標準的markdown格式回答，要有結構，可以加入emoji 要是專業的emoji 幫助閱讀用的，注意這是非常專業的報告，講解的越詳細越好，給專業投資人看的
注意，你是非常專業的財務股市分析師，所以回答都要有邏輯

不用說：好的，以下是您提供的.... ，也不用免责聲明，這種廢話，直接進入正題開始回答，所以不要說 "好的" 也不要說 "希望这些分析对您有所帮助！


"""
        
        # 打印系统提示信息统计
        prompt_char_count = len(expert_prompt)
        prompt_token_estimate = estimate_tokens(expert_prompt)
        
        print(f"\n============== {expert_name} 专家统计 ==============")
        print(f"文档数量: {documents_count} 个")
        print(f"原始专家知识库: {original_length:,} 字符")
        print(f"系统提示总字数: {prompt_char_count:,} 字符")
        print(f"系统提示估计Token数: 约 {prompt_token_estimate:,} tokens")
        print("==============================================\n")
        
        try:
            # 创建专家对象，只存储提示和模型名称，不再创建客户端
            expert = {
                "system_prompt": expert_prompt,
                "model": st.session_state.selected_model,  # 使用用户选择的模型
                "stats": {
                    "documents_count": documents_count,
                    "original_length": original_length,
                    "char_count": prompt_char_count,
                    "token_estimate": prompt_token_estimate
                }
            }
            
            # 保存专家信息到session state
            st.session_state.expert_agents[expert_name] = expert
            return expert
        except Exception as e:
            st.error(f"创建{expert_name}模型时出错: {str(e)}")
            import traceback
            st.code(traceback.format_exc(), language="python")
            return None
    
    return None

# 使用专家分析内容
def analyze_with_experts(company_content):
    """使用专家LLM分析公司内容"""
    results = {}
    
    # 打印将要分析的内容的统计信息
    input_char_count = len(company_content)
    input_token_estimate = estimate_tokens(company_content)
    print("\n============== 输入内容统计 ==============")
    print(f"输入内容总字数: {input_char_count:,} 字符")
    print(f"输入内容估计Token数: 约 {input_token_estimate:,} tokens")
    print("==============================================\n")
    
    # 创建专家回答区域
    st.subheader(f"专家分析 ({len(st.session_state.selected_experts)} 名专家)")
    
    # 预先为每个专家创建一个容器和状态占位符
    expert_containers = {}
    status_placeholders = {}
    
    # 添加CSS样式以美化专家回答区域
    st.markdown("""
    <style>
    .expert-box {
        border: 2px solid #4CAF50;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
        background-color: #f8f9fa;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .expert-header {
        font-size: 1.3em;
        font-weight: bold;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 2px solid #4CAF50;
        color: #2E7D32;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 首先创建所有专家的容器
    for i, expert_name in enumerate(st.session_state.selected_experts):
        avatar = get_expert_avatar(expert_name)
        
        # 创建专家容器，使用expander
        expert_expander = st.expander(f"{avatar} {expert_name}", expanded=True)
        expert_containers[expert_name] = expert_expander
        status_placeholders[expert_name] = expert_expander.empty()
        status_placeholders[expert_name].info(f"{avatar} {expert_name} 正在分析...")
    
    # 然后执行分析
    for expert_name in st.session_state.selected_experts:
        try:
            # 获取专家头像
            avatar = get_expert_avatar(expert_name)
            
            # 获取之前创建的状态占位符
            status_placeholder = status_placeholders[expert_name]
            
            # 创建或获取专家
            expert = create_expert_llm(expert_name)
            
            if expert:
                # 生成回答
                try:
                    # 准备输入
                    from google.genai import types
                    
                    # 合并系统提示和用户消息到一个user角色消息中
                    combined_prompt = f"请基于以下的公司信息，分析此公司的潜在风险和问题:\n\n{company_content}"
                    
                    # 记录合并后的提示统计
                    combined_prompt_chars = len(combined_prompt)
                    combined_prompt_tokens = estimate_tokens(combined_prompt)
                    print(f"\n============== {expert_name} 合并提示统计 ==============")
                    print(f"合并提示总字数: {combined_prompt_chars:,} 字符")
                    print(f"合并提示估计Token数: 约 {combined_prompt_tokens:,} tokens")
                    print("==============================================\n")
                    contents = [
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=combined_prompt)],
                        ),
                    ]
                    
                    # 配置生成参数
                    generate_content_config = types.GenerateContentConfig(
                        temperature=0.2,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=8192,
                        response_mime_type="text/plain",
                        system_instruction=[
                            types.Part.from_text(text=expert['system_prompt']),
                        ],
                    )
                    
                    # 定义带退避策略的重试函数
                    @backoff.on_exception(
                        backoff.expo, 
                        (Exception, httpx.ConnectError, httpx.ReadTimeout), 
                        max_tries=5,
                        factor=2,
                        jitter=backoff.full_jitter
                    )
                    def generate_with_retry():
                        # 为每次请求获取一个新的API密钥
                        if "google_api_key_cycle" not in st.session_state:
                            st.session_state.google_api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
                        api_key = next(st.session_state.google_api_key_cycle)
                        print(f"使用API密钥: {api_key[:5]}...{api_key[-4:]}")
                        
                        # 随机暂停一小段时间，避免并发请求过多
                        time.sleep(random.uniform(0.5, 2.0))
                        
                        # 使用新的API密钥创建客户端
                        client = genai.Client(api_key=api_key)
                        
                        try:
                            # 移除timeout参数
                            response = client.models.generate_content(
                                model=expert["model"],
                                contents=contents,
                                config=generate_content_config,
                            )
                            return response
                        except (httpx.ConnectError, httpx.ReadTimeout) as e:
                            print(f"连接错误: {str(e)}, 准备重试...")
                            raise
                        except Exception as e:
                            print(f"生成内容错误: {str(e)}, 准备重试...")
                            raise
                    
                    # 修改后的超时处理方法，不使用单独的线程来更新UI
                    def execute_with_timeout(func, timeout_seconds=60):
                        # 创建Future对象
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(func)
                            
                            # 在主线程中等待结果，同时更新倒计时
                            start_time = time.time()
                            
                            # 每0.5秒检查一次结果并更新倒计时
                            try:
                                while not future.done() and time.time() - start_time < timeout_seconds:
                                    elapsed = time.time() - start_time
                                    remaining = timeout_seconds - elapsed
                                    
                                    # 在主线程中更新UI - 合并分析状态和倒计时
                                    status_placeholder.info(f"{avatar} {expert_name} 正在分析... ⏱️ {remaining:.0f}秒")
                                    
                                    # 短暂等待，避免过高的CPU使用率
                                    time.sleep(0.5)
                                    
                                    # 尝试非阻塞地获取结果
                                    try:
                                        # 非阻塞检查
                                        result = future.result(timeout=0.01)
                                        status_placeholder.empty()
                                        return result
                                    except concurrent.futures.TimeoutError:
                                        # 继续等待
                                        pass
                                
                                # 检查是否完成
                                if future.done():
                                    status_placeholder.empty()
                                    return future.result()
                                else:
                                    # 超时
                                    status_placeholder.warning(f"{avatar} {expert_name} 响应超时，准备重试...")
                                    # 尝试取消任务
                                    future.cancel()
                                    raise TimeoutError(f"操作超时（超过{timeout_seconds}秒）")
                            
                            except Exception as e:
                                status_placeholder.warning(f"{avatar} {expert_name} 发生错误: {str(e)}")
                                # 尝试取消任务
                                future.cancel()
                                raise
                    
                    # 尝试执行API调用，最多重试5次
                    max_retries = 5
                    retry_count = 0
                    response = None
                    
                    # 在主流程中重试
                    while response is None and retry_count < max_retries:
                        try:
                            # 使用超时控制执行API调用
                            response = execute_with_timeout(generate_with_retry, 60)
                        except (TimeoutError, Exception) as e:
                            retry_count += 1
                            print(f"尝试 {retry_count}/{max_retries} 失败: {str(e)}")
                            
                            if retry_count < max_retries:
                                status_placeholder.warning(f"{avatar} {expert_name} 重试中... ({retry_count}/{max_retries})")
                                time.sleep(1)  # 短暂暂停后重试
                            else:
                                status_placeholder.error(f"{avatar} {expert_name} 最大重试次数已达到")
                                raise Exception(f"在 {max_retries} 次尝试后仍然失败: {str(e)}")
                    
                    if response:
                        # 获取结果
                        result_text = response.text
                        
                        # 记录输出结果统计
                        output_chars = len(result_text)
                        output_tokens = estimate_tokens(result_text)
                        print(f"\n============== {expert_name} 输出结果统计 ==============")
                        print(f"输出结果总字数: {output_chars:,} 字符")
                        print(f"输出结果估计Token数: 约 {output_tokens:,} tokens")
                        print("==============================================\n")
                        
                        results[expert_name] = {
                            "content": result_text,
                            "avatar": avatar,
                            "stats": {
                                "input_chars": combined_prompt_chars,
                                "input_tokens": combined_prompt_tokens,
                                "output_chars": output_chars,
                                "output_tokens": output_tokens
                            }
                        }
                        
                        # 立即显示结果
                        status_placeholder.empty()
                        with expert_containers[expert_name]:
                            # 直接使用markdown渲染专家回答内容，保持markdown格式
                            st.markdown(result_text)
                    else:
                        raise Exception("无法从API获取响应")
                    
                except Exception as e:
                    error_msg = f"多次重试后仍然生成分析失败: {str(e)}"
                    print(error_msg)  # 只在控制台显示错误
                    import traceback
                    print(traceback.format_exc())  # 只在控制台显示详细错误
                    results[expert_name] = {
                        "content": error_msg,
                        "avatar": avatar
                    }
                    # 显示错误信息
                    with expert_containers[expert_name]:
                        status_placeholder.error(f"{avatar} {expert_name} 分析失败 (多次重试后)")
                    
            else:
                results[expert_name] = {
                    "content": "无法加载专家模型",
                    "avatar": avatar
                }
                # 显示错误信息
                with expert_containers[expert_name]:
                    status_placeholder.error(f"{avatar} {expert_name} 模型加载失败")
                
        except Exception as e:
            results[expert_name] = {
                "content": f"分析失败: {str(e)}",
                "avatar": get_expert_avatar(expert_name)
            }
            # 只在控制台显示详细错误
            import traceback
            print(traceback.format_exc())
            # 显示错误信息
            with expert_containers[expert_name]:
                status_placeholder.error(f"{avatar} {expert_name} 分析失败")
    
    # 汇总所有专家的分析结果统计 - 只在终端显示
    total_output_chars = 0
    total_output_tokens = 0
    total_input_tokens = 0
    
    for expert_name, result in results.items():
        if "stats" in result:
            total_output_chars += result["stats"]["output_chars"]
            total_output_tokens += result["stats"]["output_tokens"]
            total_input_tokens += result["stats"]["input_tokens"]
    
    print("\n============== 所有专家分析结果汇总 ==============")
    print(f"专家数量: {len(results)}")
    print(f"总输出字符数: {total_output_chars:,} 字符")
    print(f"总输出估计Token数: 约 {total_output_tokens:,} tokens")
    print(f"总输入估计Token数: 约 {total_input_tokens:,} tokens")
    print(f"总Token消耗: 约 {total_input_tokens + total_output_tokens:,} tokens")
    print("==============================================\n")
    
    return results

# 执行公司分析
def run_analysis(company_name):
    # 生成关键词搜索
    keywords = [
        f"{company_name} 业绩",
        f"{company_name} 风险",
        f"{company_name} 造假"
    ]
    
    # 创建季度日期范围
    quarter_ranges = generate_quarter_ranges()
    
    # 存储所有搜索结果和内容
    all_results = []
    all_contents = []
    
    # 进度条
    progress_bar = st.progress(0)
    search_status = st.empty()
    
    # 准备所有搜索任务
    search_tasks = []
    for keyword in keywords:
        for quarter in quarter_ranges:
            search_tasks.append((keyword, quarter['start'], quarter['end']))
    
    # 显示搜索状态
    search_status.write("正在并行执行搜索请求...")
    
    # 并行执行搜索
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # 提交所有任务
        future_to_search = {
            executor.submit(run_exa_search, task[0], task[1], task[2], 20): task 
            for task in search_tasks
        }
        
        # 处理结果
        completed_searches = 0
        total_searches = len(search_tasks)
        
        for future in concurrent.futures.as_completed(future_to_search):
            completed_searches += 1
            task = future_to_search[future]
            keyword, start_date, end_date = task
            
            try:
                search_data = future.result()
                if search_data['results']:
                    all_results.extend(search_data['results'])
                
                if search_data['contents']:
                    all_contents.extend(search_data['contents'])
                
                # 更新进度条和状态信息
                progress = completed_searches / total_searches
                progress_bar.progress(progress)
                search_status.write(f"完成: {completed_searches}/{total_searches} - {search_data['keyword']} ({search_data['quarter']})")
            
            except Exception as e:
                st.error(f"处理搜索结果时出错: {str(e)}")
    
    search_status.empty()
    progress_bar.empty()
    
    # 提取所有URL和内容
    url_to_content = {}
    content_hashes = set()
    unique_contents = []
    duplicates_count = 0
    
    # 对搜索结果进行去重
    for item in all_contents:
        url = item['url']
        content = item['content']
        
        # 使用内容的哈希值来去重
        content_hash = hash(content)
        
        if content_hash not in content_hashes:
            # 这是一个新的不重复内容
            content_hashes.add(content_hash)
            unique_contents.append(item)
            url_to_content[url] = content
        else:
            # 这是重复内容
            duplicates_count += 1
    
    # 更新到去重后的内容列表
    all_contents = unique_contents
    
    # 提取所有不重复的URL
    all_urls = list(url_to_content.keys())
    
    # 计算搜索结果总字数
    total_search_chars = 0
    for item in all_contents:
        total_search_chars += len(item['content'])
    
    

    # 打印搜索结果统计信息 - 只在终端显示
    print("\n============== 搜索结果统计 ==============")
    print(f"搜索结果数: {len(all_results)} 条")
    print(f"独特URL数: {len(all_urls)} 个")
    print(f"去除重复内容: {duplicates_count} 个")
    print(f"搜索结果总字数: {total_search_chars:,} 字符")
    print(f"搜索结果估计Token数: 约 {estimate_tokens(str(total_search_chars))} tokens")
    print("==============================================\n")
    
    # 处理内容
    if all_contents:
        st.markdown("成功获取内容: {} 个网页".format(len(all_contents)))
        
        # 合并所有内容
        combined_text = []
        for item in all_contents:
            combined_text.append(f"URL: {item['url']}\n\n{item['content']}\n\n---\n\n")
        
        combined_content = "".join(combined_text)
        combined_content_chars = len(combined_content)
        combined_content_tokens = estimate_tokens(combined_content)
        
        # 只在终端显示合并内容的统计信息
        print("\n============== 合并内容统计 ==============")
        print(f"合并后内容总字数: {combined_content_chars:,} 字符")
        print(f"合并后内容估计Token数: 约 {combined_content_tokens:,} tokens")
        print("==============================================\n")
        
        # 如果开启了显示搜索结果选项，则显示搜索结果
        if st.session_state.show_search_results:
            search_results_container = st.expander("查看搜索结果", expanded=True)
            with search_results_container:
                for i, item in enumerate(all_contents):
                    st.markdown(f"### 结果 {i+1}: {item['url']}")
                    st.text_area(f"内容 {i+1}", item['content'], height=200, key=f"content_{i}")
                    st.markdown("---")
        
        # 开始专家分析
        if combined_content:
            # 使用专家分析
            expert_results = analyze_with_experts(combined_content)
            
            # 保存结果到session state
            st.session_state.analysis_results = expert_results
        else:
            st.warning("未获取到网页内容，无法进行专家分析")
    else:
        st.warning("未找到相关网页")
    
    # 分析完成
    st.session_state.should_run_analysis = False

# 检查数据目录和初始化专家列表
if 'expert_names_loaded' not in st.session_state:
    expert_dir = Path("data_short_expert")
    
    if expert_dir.exists() and any(expert_dir.iterdir()):
        st.session_state.expert_names = get_expert_names()
        # 默认选中指定的专家
        st.session_state.selected_experts = [expert for expert in DEFAULT_EXPERTS if expert in st.session_state.expert_names]
        st.session_state.expert_names_loaded = True
    else:
        with st.spinner("正在初始化专家数据..."):
            if initialize_dropbox():
                st.session_state.expert_names = get_expert_names()
                # 默认选中指定的专家
                st.session_state.selected_experts = [expert for expert in DEFAULT_EXPERTS if expert in st.session_state.expert_names]
                st.session_state.expert_names_loaded = True
            else:
                st.error("无法初始化专家数据。请确保数据目录存在或配置正确。")

# 侧边栏配置
with st.sidebar:
    st.title("🔍 Risk Scanner 设置")
    
    # 系统配置选项
    st.subheader("⚙️ 模型设置")
    # 添加模型选择选项
    selected_model = st.radio(
        "选择分析模型",
        options=["gemini-2.5-flash", "gemini-2.5-pro"],
        index=0 if st.session_state.selected_model == "gemini-2.5-flash" else 1,
        help="选择用于分析的AI模型",
        key="model_selector"
    )
    
    # 更新会话状态中的模型选择
    if selected_model != st.session_state.selected_model:
        st.session_state.selected_model = selected_model
        # 当模型改变时，清空专家代理缓存
        st.session_state.expert_agents = {}
        st.success(f"已切换至 {selected_model} 模型")
    
    # 显示专家列表
    st.header("💡 专家列表")
    
    # 全选/取消全选按钮
    if st.button("全选" if len(st.session_state.selected_experts) < len(st.session_state.expert_names) else "取消全选"):
        if len(st.session_state.selected_experts) < len(st.session_state.expert_names):
            st.session_state.selected_experts = st.session_state.expert_names.copy()
        else:
            st.session_state.selected_experts = []
    
    # 对专家名单进行排序，将"Publication"开头的放在最后
    sorted_experts = sorted(st.session_state.expert_names, 
                          key=lambda x: (1 if x.startswith("Publication") else 0, x))
    
    # 专家选择
    for expert_name in sorted_experts:
        avatar = get_expert_avatar(expert_name)
        col1, col2 = st.columns([0.7, 3])
        
        with col1:
            is_selected = expert_name in st.session_state.selected_experts
            if st.checkbox(
                label=f"选择{expert_name}",
                value=is_selected,
                key=f"check_{expert_name}",
                label_visibility="collapsed"
            ):
                if expert_name not in st.session_state.selected_experts:
                    st.session_state.selected_experts.append(expert_name)
            else:
                if expert_name in st.session_state.selected_experts:
                    st.session_state.selected_experts.remove(expert_name)
        
        with col2:
            st.markdown(f"{avatar} {expert_name}")
    
    # 添加分隔线
    st.markdown("---")
    
    # 更新按钮
    if st.button("🔄 更新专家列表", type="primary"):
        with st.spinner("正在更新专家资料..."):
            if initialize_dropbox():
                # 清除现有专家模型
                st.session_state.expert_agents = {}
                # 默认选中指定的专家
                st.session_state.selected_experts = [expert for expert in DEFAULT_EXPERTS if expert in st.session_state.expert_names]
                st.success("专家资料更新成功！")
                st.rerun()
            else:
                st.error("更新失败，请检查网络连接或配置。")

# 主界面内容（不使用列分割，直接在主区域放置内容）
st.title("🔍 Risk Scanner")
st.write("输入公司名称，扫描潜在欺诈风险")

# 使用表单确保只有按Enter才提交
with st.form(key="search_form"):
    company_name = st.text_input("公司名称", placeholder="例如：阿里巴巴 (输入后按Enter执行分析)")
    # 显示提交按钮
    submit_button = st.form_submit_button("开始分析", type="primary")

# 只有当表单提交时才执行分析
if submit_button and company_name:
    # 更新状态
    st.session_state.company_name = company_name
    st.session_state.should_run_analysis = True

# 当需要执行分析时
if st.session_state.should_run_analysis and company_name:
    # 检查是否选择了专家
    if not st.session_state.selected_experts:
        st.warning("请在侧边栏选择至少一位专家进行分析")
        st.session_state.should_run_analysis = False
    else:
        # 执行分析
        run_analysis(company_name)

# 如果有之前的分析结果，显示它们
elif st.session_state.analysis_results and not st.session_state.should_run_analysis:
    # 显示专家分析结果
    st.subheader(f"专家分析 ({len(st.session_state.analysis_results)} 名专家)")
    
    # 添加CSS样式以美化专家回答区域
    st.markdown("""
    <style>
    .expert-box {
        border: 2px solid #4CAF50;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
        background-color: #f8f9fa;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .expert-header {
        font-size: 1.3em;
        font-weight: bold;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 2px solid #4CAF50;
        color: #2E7D32;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 显示每个专家的结果，并为每个专家添加单独的容器
    for i, (expert_name, result) in enumerate(st.session_state.analysis_results.items()):
        # 创建专家容器，使用expander
        with st.expander(f"{result['avatar']} {expert_name}", expanded=True):
            # 直接使用markdown渲染内容
            st.markdown(result['content']) 