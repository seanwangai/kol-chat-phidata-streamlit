"""
SEC & 财报会议记录分析师 - Production级别
专业的财务数据综合分析平台

Features:
- SEC文件获取和分析
- 财报会议记录获取和分析
- AI驱动的文档处理
- 实时进度跟踪
- 错误处理和重试机制
- 缓存优化
"""

import streamlit as st
import os
import json
import requests
import warnings
import logging
import time
import hashlib
import tempfile
import uuid
import fitz  # PyMuPDF for PDF processing
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, fields
from functools import lru_cache
from contextlib import contextmanager
import re
import html
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 配置选项：是否保存transcript文件到磁盘
SAVE_TRANSCRIPT_FILES = os.getenv("SAVE_TRANSCRIPT_FILES", "false").lower() == "true"

# 第三方库
from sec_edgar_api import EdgarClient
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import httpx
from google import genai
from google.genai import types
from itertools import cycle
from newspaper import Article

# 页面配置
try:
    st.set_page_config(
        page_title="SEC & 财报会议记录分析师",
        page_icon="📊",
        layout="wide"
    )
except Exception:
    # 静默处理页面配置错误
    pass

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 语言配置
LANGUAGE_CONFIG = {
    "English": {
        "title": "📊 Saudi Exchange Chat",
        "sidebar_header": "📋 Configuration",
        "ticker_label": "Ticker",
        "ticker_placeholder": "e.g., AAPL, 1024 HK, 2222 SA",
        "years_label": "Years of Data",
        "data_type_header": "📄 Data Type",
        "sec_reports_us": "Quarterly & Annual (10-K, 10-Q, 20-F, 6-K, 424B4)",
        "sec_others_us": "Others (8-K, S-8, DEF 14A, F-3)",
        "sec_reports_hk": "Quarterly & Annual Results",
        "sec_others_hk": "Other Announcements",
        "earnings_label": "Earnings Call Transcripts",
        "earnings_caption": "Earnings call transcripts",
        "model_header": "🤖 AI Model",
        "model_label": "Select Model",
        "analysis_mode_header": "⚡ Analysis Mode",
        "analysis_mode_label": "Select Mode",
        "fast_mode": "Fast Mode",
        "detailed_mode": "Detailed Mode",
        "fast_mode_caption": "Analyze all documents together in one pass",
        "detailed_mode_caption": "Analyze each document separately, then integrate results",
        "api_header": "💳 API Configuration",
        "access_code_label": "Enter Access Code",
        "access_code_placeholder": "Enter access code to enable premium API",
        "premium_enabled": "✅ Premium API Service Enabled",
        "free_api": "ℹ️ Using Free API Service",
        "access_code_error": "❌ Invalid Access Code",
        "premium_success": "🎉 Premium API Service Enabled!",
        "language_header": "🌐 Language",
        "language_label": "Select Language",
        "hk_stock_info": "🏢 Hong Kong Stock - Standardized to: {}",
        "us_stock_info": "🇺🇸 US Stock",
        "saudi_stock_info": "🇸🇦 Saudi Stock",
        "chat_placeholder": "Please enter your question...",
        "status_header": "📋 STATUS",
        "stop_button": "⏹️ Stop Processing",
        "progress_text": "Progress: {}/{} documents",
        "stop_success": "⏹️ Processing stopped by user",
        "processing_stopped": "Processing has been stopped by user request."
    },
    "中文": {
        "title": "📊 沙特交易所聊天",
        "sidebar_header": "📋 Configuration",
        "ticker_label": "Ticker",
        "ticker_placeholder": "e.g., AAPL, 1024 HK, 2222 SA",
        "years_label": "数据年份",
        "data_type_header": "📄 Data Type",
        "sec_reports_us": "Quarterly & Annual (10-K, 10-Q, 20-F, 6-K, 424B4)",
        "sec_others_us": "Others (8-K, S-8, DEF 14A, F-3)",
        "sec_reports_hk": "Quarterly & Annual Results",
        "sec_others_hk": "Other Announcements",
        "earnings_label": "Earnings Call Transcripts",
        "earnings_caption": "Earnings call transcripts",
        "model_header": "🤖 AI Model",
        "model_label": "Select Model",
        "analysis_mode_header": "⚡ 分析模式",
        "analysis_mode_label": "选择模式",
        "fast_mode": "快速模式",
        "detailed_mode": "详细模式",
        "fast_mode_caption": "一次性分析所有文档",
        "detailed_mode_caption": "逐个分析每份文档，然后整合结果",
        "api_header": "💳 API Configuration",
        "access_code_label": "Enter Access Code",
        "access_code_placeholder": "Enter access code to enable premium API",
        "premium_enabled": "✅ Premium API Service Enabled",
        "free_api": "ℹ️ Using Free API Service",
        "access_code_error": "❌ Invalid Access Code",
        "premium_success": "🎉 Premium API Service Enabled!",
        "language_header": "🌐 Language",
        "language_label": "Select Language",
        "hk_stock_info": "🏢 港股 - 已标准化为: {}",
        "us_stock_info": "🇺🇸 美股",
        "saudi_stock_info": "🇸🇦 沙特股票",
        "chat_placeholder": "请输入您的问题...",
        "status_header": "📋 STATUS",
        "stop_button": "⏹️ 停止处理",
        "progress_text": "Progress: {}/{} documents",
        "stop_success": "⏹️ 用户已停止处理",
        "processing_stopped": "处理已被用户停止。"
    },
    "العربية": {
        "title": "📊 دردشة السوق السعودية",
        "sidebar_header": "📋 الإعدادات",
        "ticker_label": "رمز السهم",
        "ticker_placeholder": "مثال: AAPL, 1024 HK, 2222 SA",
        "years_label": "سنوات البيانات",
        "data_type_header": "📄 نوع البيانات",
        "sec_reports_us": "التقارير الفصلية والسنوية (10-K, 10-Q, 20-F, 6-K, 424B4)",
        "sec_others_us": "أخرى (8-K, S-8, DEF 14A, F-3)",
        "sec_reports_hk": "النتائج الفصلية والسنوية",
        "sec_others_hk": "إعلانات أخرى",
        "earnings_label": "نصوص مكالمات الأرباح",
        "earnings_caption": "نصوص مكالمات الأرباح",
        "model_header": "🤖 نموذج الذكاء الاصطناعي",
        "model_label": "اختر النموذج",
        "analysis_mode_header": "⚡ وضع التحليل",
        "analysis_mode_label": "اختر الوضع",
        "fast_mode": "الوضع السريع",
        "detailed_mode": "الوضع المفصل",
        "fast_mode_caption": "تحليل جميع المستندات معاً في مرة واحدة",
        "detailed_mode_caption": "تحليل كل مستند على حدة، ثم دمج النتائج",
        "api_header": "💳 إعدادات واجهة برمجة التطبيقات",
        "access_code_label": "أدخل رمز الوصول",
        "access_code_placeholder": "أدخل رمز الوصول لتفعيل خدمة API المميزة",
        "premium_enabled": "✅ تم تفعيل خدمة API المميزة",
        "free_api": "ℹ️ استخدام خدمة API المجانية",
        "access_code_error": "❌ رمز وصول غير صحيح",
        "premium_success": "🎉 تم تفعيل خدمة API المميزة!",
        "language_header": "🌐 اللغة",
        "language_label": "اختر اللغة",
        "hk_stock_info": "🏢 سهم هونغ كونغ - تم التوحيد القياسي إلى: {}",
        "us_stock_info": "🇺🇸 سهم أمريكي",
        "saudi_stock_info": "🇸🇦 سهم سعودي",
        "chat_placeholder": "يرجى إدخال سؤالك...",
        "status_header": "📋 الحالة",
        "stop_button": "⏹️ إيقاف المعالجة",
        "progress_text": "التقدم: {}/{} مستند",
        "stop_success": "⏹️ تم إيقاف المعالجة بواسطة المستخدم",
        "processing_stopped": "تم إيقاف المعالجة بناءً على طلب المستخدم."
    }
}

# 常量配置
@dataclass
class Config:
    """应用配置"""
    # 模型配置
    MODELS: Dict[str, str] = field(default_factory=lambda: {
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.5-pro": "Gemini 2.5 Pro"
    })
    
    # SEC配置
    SEC_USER_AGENT: str = "SEC Earnings Analyzer <analysis@example.com>"
    SEC_FORMS: List[str] = field(default_factory=lambda: [
        '10-K', '10-Q', '8-K', '20-F', '6-K', '424B4', 'DEF 14A', 'S-8'
    ])
    
    # 请求配置
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    
    # 内容限制
    MAX_CONTENT_LENGTH: int = 900000
    
    # 缓存配置
    CACHE_TTL: int = 3600  # 1小时
    
    # 日期解析格式
    DATE_FORMATS: List[str] = field(default_factory=lambda: [
        '%B %d, %Y',    # January 1, 2023
        '%b %d, %Y',    # Jan 1, 2023
        '%Y-%m-%d',     # 2023-01-01
        '%m/%d/%Y',     # 01/01/2023
    ])
    
    # 日期模式
    DATE_PATTERNS: List[str] = field(default_factory=lambda: [
        r'\b\w+ \d{1,2}, \d{4}\b',  # January 1, 2023
        r'\b\d{4}-\d{1,2}-\d{1,2}\b',  # 2023-01-01
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',  # 01/01/2023
    ])

config = Config()

# 数据类定义
@dataclass
class Document:
    """文档数据类"""
    type: str
    title: str
    date: datetime.date
    url: str
    content: Optional[str] = None
    form_type: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[int] = None
    temp_file_path: Optional[str] = None  # 添加临时文件路径字段

@dataclass
class ProcessingStatus:
    """处理状态数据类"""
    is_processing: bool = False
    current_step: Optional[str] = None
    completed_documents: int = 0
    total_documents: int = 0
    document_results: List[Dict] = field(default_factory=list)
    processing_step: int = 0
    processing_prompt: str = ""
    integration_prompt: str = ""
    documents: List[Document] = field(default_factory=list)
    user_question: str = ""
    error_message: Optional[str] = None
    status_messages: List[str] = field(default_factory=list)
    current_status_label: str = ""
    progress_percentage: float = 0.0
    stop_requested: bool = False

    def __post_init__(self):
        # Ensure fields are initialized if not provided
        if self.processing_step is None:
            self.processing_step = 0
        if self.completed_documents is None:
            self.completed_documents = 0
        if self.total_documents is None:
            self.total_documents = 0
        if self.document_results is None:
            self.document_results = []
        if self.processing_prompt is None:
            self.processing_prompt = ""
        if self.integration_prompt is None:
            self.integration_prompt = ""
        if self.documents is None:
            self.documents = []
        if self.user_question is None:
            self.user_question = ""
        if self.error_message is None:
            self.error_message = None
        if self.status_messages is None:
            self.status_messages = []
        if self.current_status_label is None:
            self.current_status_label = ""
        if self.progress_percentage is None:
            self.progress_percentage = 0.0
        if self.stop_requested is None:
            self.stop_requested = False
    
    def add_status_message(self, message: str):
        """添加状态消息"""
        self.status_messages.append(f"⏱️ {datetime.now().strftime('%H:%M:%S')} - {message}")
        # 只保留最近的20条消息
        if len(self.status_messages) > 20:
            self.status_messages = self.status_messages[-20:]
    
    def update_progress(self, completed: int, total: int, label: str = ""):
        """更新进度"""
        self.completed_documents = completed
        self.total_documents = total
        self.progress_percentage = (completed / total) * 100 if total > 0 else 0
        self.current_status_label = label

# 异常类定义
class SECAnalyzerError(Exception):
    """SEC分析器基础异常"""
    pass

class APIError(SECAnalyzerError):
    """API调用异常"""
    pass

class DataRetrievalError(SECAnalyzerError):
    """数据获取异常"""
    pass

class DateParsingError(SECAnalyzerError):
    """日期解析异常"""
    pass

# 工具类
def is_hk_stock(ticker: str) -> bool:
    """检测是否为港股代码"""
    if not ticker:
        return False
    
    ticker_upper = ticker.upper().strip()
    
    # 检查是否以.HK结尾
    if ticker_upper.endswith('.HK'):
        return True
    
    # 检查是否是 "数字 HK" 格式
    if ' HK' in ticker_upper:
        return True
    
    # 检查是否是纯数字，但排除4位数字（优先给沙特交易所）
    ticker_clean = ticker.strip()
    if ticker_clean.isdigit() and len(ticker_clean) != 4:
        return True
    
    return False

def is_saudi_stock(ticker: str) -> bool:
    """检测是否为沙特交易所代码"""
    if not ticker:
        return False
    
    ticker_upper = ticker.upper().strip()
    
    # 检查是否以.SA结尾
    if ticker_upper.endswith('.SA'):
        return True
    
    # 检查是否是 "数字 SA" 格式
    if ' SA' in ticker_upper:
        return True
    
    # 检查是否是数字（沙特交易所代码通常是数字，优先识别）
    ticker_clean = ticker.strip()
    if ticker_clean.isdigit():
        return True
    
    return False

def normalize_saudi_ticker(ticker: str) -> str:
    """标准化沙特交易所代码为 XXXX 格式（4位数字）"""
    if not ticker:
        return ""
    
    ticker_clean = ticker.upper().strip()
    
    # 移除.SA后缀
    if ticker_clean.endswith('.SA'):
        ticker_clean = ticker_clean[:-3]
    
    # 移除空格和SA
    if ' SA' in ticker_clean:
        ticker_clean = ticker_clean.replace(' SA', '')
    
    # 确保是4位数字
    if ticker_clean.isdigit():
        return ticker_clean.zfill(4)  # 补零到4位
    
    return ticker_clean

def normalize_hk_ticker(ticker: str) -> str:
    """标准化港股代码为 XXXX.HK 格式，自動補0成四位數"""
    if not ticker:
        return ticker
    
    ticker_clean = ticker.strip()
    
    # 如果已经是标准格式，提取數字部分處理
    if ticker_clean.upper().endswith('.HK'):
        number_part = ticker_clean.upper().replace('.HK', '').strip()
        if number_part.isdigit():
            # 補0成四位數
            padded_number = number_part.zfill(4)
            return f"{padded_number}.HK"
        return ticker_clean.upper()
    
    # 处理 "数字 HK" 格式
    if ' HK' in ticker_clean.upper():
        number_part = ticker_clean.upper().replace(' HK', '').strip()
        if number_part.isdigit():
            # 補0成四位數
            padded_number = number_part.zfill(4)
            return f"{padded_number}.HK"
    
    # 处理纯数字
    if ticker_clean.isdigit():
        # 補0成四位數
        padded_number = ticker_clean.zfill(4)
        return f"{padded_number}.HK"
    
    # 其他情况返回原值
    return ticker_clean.upper()

def clean_hk_ticker(ticker: str) -> str:
    """清理港股代码，移除.HK后缀，返回纯数字"""
    normalized = normalize_hk_ticker(ticker)
    return normalized.replace('.HK', '').replace('.hk', '')

class RateLimiter:
    """API请求限流器"""
    def __init__(self, max_calls: int = 30, window: int = 60):
        self.max_calls = max_calls
        self.window = window
        self.calls = []
    
    def wait_if_needed(self):
        """如果需要，等待直到可以发出请求"""
        now = time.time()
        self.calls = [call_time for call_time in self.calls if now - call_time < self.window]
        
        if len(self.calls) >= self.max_calls:
            wait_time = self.window - (now - self.calls[0])
            if wait_time > 0:
                time.sleep(wait_time)
                self.calls = []
        
        self.calls.append(now)

class CacheManager:
    """缓存管理器"""
    def __init__(self):
        # Session state is now initialized by SessionManager
        pass
    
    def get_cache_key(self, *args) -> str:
        """生成缓存键"""
        key_string = "|".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, key: str, default=None):
        """获取缓存值"""
        cache_data = st.session_state.cache.get(key)
        if cache_data:
            timestamp, value = cache_data
            if time.time() - timestamp < config.CACHE_TTL:
                return value
            else:
                # 缓存过期，删除
                del st.session_state.cache[key]
        return default
    
    def set(self, key: str, value: Any):
        """设置缓存值"""
        st.session_state.cache[key] = (time.time(), value)
    
    def clear(self):
        """清空缓存"""
        st.session_state.cache.clear()

class DocumentManager:
    """文档管理器，负责保存和管理临时文件"""
    
    def __init__(self):
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="sec_analyzer_")
        logger.info(f"创建临时目录: {self.temp_dir}")
    
    def save_document_content(self, document: Document) -> str:
        """保存文档内容到临时文件并返回文件路径"""
        try:
            # 生成唯一的文件名
            file_id = str(uuid.uuid4())[:8]
            safe_title = re.sub(r'[^\w\-_\.]', '_', document.title)
            filename = f"{file_id}_{safe_title}.txt"
            file_path = os.path.join(self.temp_dir, filename)
            
            # 保存内容
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"文档标题: {document.title}\n")
                f.write(f"文档类型: {document.type}\n")
                f.write(f"文档日期: {document.date}\n")
                f.write(f"原始URL: {document.url}\n")
                f.write("="*80 + "\n\n")
                f.write(document.content or "内容为空")
            
            document.temp_file_path = file_path
            logger.info(f"文档已保存到临时文件: {filename}")
            return file_path
            
        except Exception as e:
            logger.error(f"保存文档内容失败: {e}")
            return None
    
    def get_download_content(self, file_path: str) -> Optional[bytes]:
        """获取文件内容用于下载"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().encode('utf-8')
        except Exception as e:
            logger.error(f"读取文件内容失败: {e}")
            return None
    
    def cleanup(self):
        """清理临时文件"""
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")
        except Exception as e:
            logger.error(f"清理临时目录失败: {e}")

class SixKProcessor:
    """6-K文件处理器"""
    
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.headers = {"User-Agent": config.SEC_USER_AGENT}
    
    def process_6k_filing(self, ticker: str, cik: str, filing_url: str, document: Document) -> List[Document]:
        """处理6-K文件，下载附件并提取ex99文件"""
        try:
            logger.info(f"🔍 [6K-DEBUG] 开始处理6-K文件: {ticker}")
            logger.info(f"🔍 [6K-DEBUG] 文件URL: {filing_url}")
            logger.info(f"🔍 [6K-DEBUG] CIK: {cik}")
            
            # 从URL中提取accession number（无破折号格式）
            # URL格式：https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_no_dashes}/{primary_doc}
            accession_match = re.search(r'/(\d{18})/', filing_url)
            if not accession_match:
                logger.error(f"❌ [6K-DEBUG] 无法从URL中提取accession number: {filing_url}")
                return []  # 返回空列表
            
            accession_no_no_dashes = accession_match.group(1)
            # 重新构造带破折号的格式用于显示
            accession_no = f"{accession_no_no_dashes[:10]}-{accession_no_no_dashes[10:12]}-{accession_no_no_dashes[12:]}"
            
            logger.info(f"🔍 [6K-DEBUG] 提取到的accession number: {accession_no}")
            
            # 创建6-K文件专用目录
            filing_dir = os.path.join(self.temp_dir, f"6K_{ticker}_{accession_no}")
            os.makedirs(filing_dir, exist_ok=True)
            logger.info(f"🔍 [6K-DEBUG] 创建目录: {filing_dir}")
            
            logger.info(f"🔍 [6K-DEBUG] 开始下载附件...")
            
            # 下载所有附件
            attachments = self._download_6k_attachments(cik, accession_no_no_dashes, filing_dir)
            
            logger.info(f"🔍 [6K-DEBUG] 下载附件结果: {len(attachments) if attachments else 0} 个文件")
            if attachments:
                logger.info(f"🔍 [6K-DEBUG] 附件列表: {[os.path.basename(f) for f in attachments]}")
            
            if not attachments:
                logger.warning(f"⚠️ [6K-DEBUG] 未找到6-K附件: {ticker} - {accession_no}")
                return []  # 返回空列表而不是原文档
            
            logger.info(f"🔍 [6K-DEBUG] 开始处理ex99文件...")
            
            # 处理ex99文件
            ex99_documents = self._process_ex99_files(attachments, filing_dir, document, ticker)
            
            logger.info(f"🔍 [6K-DEBUG] ex99处理结果: {len(ex99_documents) if ex99_documents else 0} 个文档")
            
            if not ex99_documents:
                logger.info(f"ℹ️ [6K-DEBUG] 未找到ex99文件: {ticker} - {accession_no} (这可能是正常情况)")
                return []  # 返回空列表而不是原文档
            
            logger.info(f"✅ [6K-DEBUG] 成功处理6-K文件，生成 {len(ex99_documents)} 个文档")
            for i, doc in enumerate(ex99_documents):
                logger.info(f"🔍 [6K-DEBUG] 文档{i+1}: {doc.title}, 内容长度: {len(doc.content) if doc.content else 0}")
            
            return ex99_documents
            
        except Exception as e:
            logger.error(f"❌ [6K-DEBUG] 处理6-K文件失败: {str(e)}")
            import traceback
            logger.error(f"❌ [6K-DEBUG] 详细错误信息: {traceback.format_exc()}")
            return []  # 返回空列表而不是原文档
    
    def _download_6k_attachments(self, cik: str, accession_no_no_dashes: str, filing_dir: str) -> List[str]:
        """下载6-K文件的所有附件，只下载pdf/htm/html文件"""
        base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_no_dashes}/"
        index_url = base_url + "index.json"
        
        logger.info(f"🔍 [6K-ATTACH] 开始下载附件，index URL: {index_url}")
        
        try:
            response = httpx.get(index_url, headers=self.headers, timeout=config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            logger.info(f"🔍 [6K-ATTACH] index.json 下载成功，状态码: {response.status_code}")
            
            index_data = response.json()
            directory = index_data.get('directory', {})
            items = directory.get('item', [])
            
            logger.info(f"🔍 [6K-ATTACH] index.json 解析成功，找到 {len(items)} 个项目")
            
            if not items:
                logger.warning(f"⚠️ [6K-ATTACH] 6-K文件无附件列表: {index_url}")
                return []
            
            # 筛选只需要的文件类型
            target_files = []
            logger.info(f"🔍 [6K-ATTACH] 开始筛选目标文件类型...")
            
            for i, item in enumerate(items):
                file_name = item.get('name', '')
                if not file_name:
                    continue
                
                logger.info(f"🔍 [6K-ATTACH] 文件{i+1}: {file_name}")
                
                # 检查文件扩展名
                ext = os.path.splitext(file_name)[1].lower()
                if ext in ['.pdf', '.htm', '.html']:
                    target_files.append(item)
                    logger.info(f"✅ [6K-ATTACH] 文件{i+1} {file_name} 符合条件 (扩展名: {ext})")
                else:
                    logger.info(f"⏭️ [6K-ATTACH] 跳过非目标文件类型: {file_name} (扩展名: {ext})")
            
            if not target_files:
                logger.warning(f"⚠️ [6K-ATTACH] 未找到pdf/htm/html文件")
                return []
            
            downloaded_files = []
            logger.info(f"🔍 [6K-ATTACH] 找到 {len(target_files)} 个目标文件，开始下载...")
            
            for i, item in enumerate(target_files):
                file_name = item.get('name', '')
                file_url = base_url + file_name
                file_path = os.path.join(filing_dir, file_name)
                
                logger.info(f"🔍 [6K-ATTACH] 下载文件{i+1}: {file_name}")
                logger.info(f"🔍 [6K-ATTACH] 文件URL: {file_url}")
                
                try:
                    file_response = httpx.get(file_url, headers=self.headers, timeout=config.REQUEST_TIMEOUT)
                    file_response.raise_for_status()
                    
                    logger.info(f"🔍 [6K-ATTACH] 文件{i+1}下载成功，状态码: {file_response.status_code}")
                    logger.info(f"🔍 [6K-ATTACH] 文件大小: {len(file_response.content)} bytes")
                    
                    # 判断文件类型并保存
                    content_type = file_response.headers.get('content-type', '').lower()
                    logger.info(f"🔍 [6K-ATTACH] 文件{i+1}内容类型: {content_type}")
                    
                    if 'text' in content_type or 'html' in content_type or 'xml' in content_type:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(file_response.text)
                        logger.info(f"🔍 [6K-ATTACH] 文件{i+1}保存为文本文件")
                    else:
                        with open(file_path, 'wb') as f:
                            f.write(file_response.content)
                        logger.info(f"🔍 [6K-ATTACH] 文件{i+1}保存为二进制文件")
                    
                    downloaded_files.append(file_path)
                    logger.info(f"✅ [6K-ATTACH] 已下载6-K附件: {file_name}")
                    
                except Exception as e:
                    logger.warning(f"❌ [6K-ATTACH] 下载6-K附件失败 {file_name}: {str(e)}")
                    import traceback
                    logger.warning(f"❌ [6K-ATTACH] 详细错误: {traceback.format_exc()}")
            
            logger.info(f"✅ [6K-ATTACH] 成功下载 {len(downloaded_files)} 个6-K目标附件")
            return downloaded_files
            
        except Exception as e:
            logger.error(f"❌ [6K-ATTACH] 获取6-K附件列表失败: {str(e)}")
            import traceback
            logger.error(f"❌ [6K-ATTACH] 详细错误信息: {traceback.format_exc()}")
            return []
    
    def _process_ex99_files(self, attachments: List[str], filing_dir: str, original_doc: Document, ticker: str) -> List[Document]:
        """处理ex99文件，按照要求分类处理HTML和PDF"""
        logger.info(f"🔍 [6K-EX99] 开始处理ex99文件，输入附件数量: {len(attachments)}")
        logger.info(f"🔍 [6K-EX99] 附件文件列表: {[os.path.basename(f) for f in attachments]}")
        
        ex99_files = []
        
        # 找到所有包含_ex99的文件
        logger.info(f"🔍 [6K-EX99] 搜索包含'ex99'的文件...")
        
        for i, file_path in enumerate(attachments):
            file_name = os.path.basename(file_path).lower()
            logger.info(f"🔍 [6K-EX99] 检查文件{i+1}: {file_name}")
            
            if 'ex99' in file_name:
                ex99_files.append(file_path)
                logger.info(f"✅ [6K-EX99] 找到ex99文件: {file_name}")
            else:
                logger.info(f"⏭️ [6K-EX99] 非ex99文件: {file_name}")
        
        if not ex99_files:
            logger.info(f"ℹ️ [6K-EX99] 未找到包含'ex99'的文件")
            logger.info(f"🔍 [6K-EX99] 完整文件名列表用于调试: {[os.path.basename(f) for f in attachments]}")
            return []
        
        logger.info(f"✅ [6K-EX99] 找到 {len(ex99_files)} 个ex99文件: {[os.path.basename(f) for f in ex99_files]}")
        
        # 分类处理不同类型的文件
        html_files = []
        pdf_files = []
        
        logger.info(f"🔍 [6K-EX99] 开始按文件类型分类...")
        
        for file_path in ex99_files:
            ext = os.path.splitext(file_path)[1].lower()
            file_name = os.path.basename(file_path)
            
            if ext in ['.html', '.htm']:
                html_files.append(file_path)
                logger.info(f"📄 [6K-EX99] HTML文件: {file_name}")
            elif ext == '.pdf':
                pdf_files.append(file_path)
                logger.info(f"📄 [6K-EX99] PDF文件: {file_name}")
            else:
                logger.info(f"⚠️ [6K-EX99] 跳过不支持的文件类型: {file_path} (扩展名: {ext})")
        
        documents = []
        
        # 处理HTML/HTM文件 - 转换为markdown后检查是否可以合并
        if html_files:
            logger.info(f"处理 {len(html_files)} 个HTML文件")
            
            # 先转换所有HTML文件为markdown
            html_contents = []
            for file_path in html_files:
                content = self._convert_html_to_markdown(file_path)
                if content:
                    file_name = os.path.basename(file_path)
                    html_contents.append({
                        'file_name': file_name,
                        'content': content
                    })
            
            if html_contents:
                # 计算总字符数
                total_chars = sum(len(item['content']) for item in html_contents)
                
                if total_chars <= config.MAX_CONTENT_LENGTH:
                    # 合并所有HTML内容
                    combined_content = ""
                    for item in html_contents:
                        combined_content += f"\n\n=== {item['file_name']} ===\n\n{item['content']}"
                    
                    html_doc = Document(
                        type=original_doc.type,
                        title=f"{ticker} 6-K ex99 files",
                        date=original_doc.date,
                        url=original_doc.url,
                        content=combined_content.strip(),
                        form_type="6-K-Ex99-HTML-Combined"
                    )
                    documents.append(html_doc)
                    logger.info(f"HTML文件已合并处理，总字符数: {total_chars}")
                else:
                    # 分别处理每个HTML文件
                    for i, item in enumerate(html_contents):
                        html_doc = Document(
                            type=original_doc.type,
                            title=f"{ticker} 6-K ex99-{i+1}",
                            date=original_doc.date,
                            url=original_doc.url,
                            content=item['content'],
                            form_type="6-K-Ex99-HTML"
                        )
                        documents.append(html_doc)
                    logger.info(f"HTML文件分别处理，总字符数超过限制: {total_chars}")
        
        # 处理PDF文件 - 必须分开处理
        if pdf_files:
            logger.info(f"处理 {len(pdf_files)} 个PDF文件")
            
            for i, file_path in enumerate(pdf_files):
                content = self._convert_pdf_to_text(file_path)
                if content:
                    file_name = os.path.basename(file_path)
                    pdf_doc = Document(
                        type=original_doc.type,
                        title=f"{ticker} 6-K ex99 PDF-{i+1}",
                        date=original_doc.date,
                        url=original_doc.url,
                        content=content,
                        form_type="6-K-Ex99-PDF"
                    )
                    documents.append(pdf_doc)
                    logger.info(f"PDF文件已处理: {file_name}")
                else:
                    logger.warning(f"PDF文件转换失败: {file_path}")
        
        logger.info(f"Ex99文件处理完成，生成 {len(documents)} 个文档")
        return documents
    
    def _convert_html_to_markdown(self, file_path: str) -> str:
        """将HTML转换为markdown格式的文本"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 处理表格 - 保持结构
            for table in soup.find_all('table'):
                # 简单的表格转换
                rows = table.find_all('tr')
                table_text = "\n"
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        table_text += "| " + " | ".join(cell_texts) + " |\n"
                table_text += "\n"
                table.replace_with(table_text)
            
            # 处理标题
            for i in range(1, 7):
                for heading in soup.find_all(f'h{i}'):
                    heading_text = heading.get_text(strip=True)
                    heading.replace_with(f"\n{'#' * i} {heading_text}\n")
            
            # 处理段落
            for p in soup.find_all('p'):
                p_text = p.get_text(strip=True)
                if p_text:
                    p.replace_with(f"\n{p_text}\n")
            
            # 处理列表
            for ul in soup.find_all('ul'):
                items = ul.find_all('li')
                list_text = "\n"
                for item in items:
                    item_text = item.get_text(strip=True)
                    if item_text:
                        list_text += f"- {item_text}\n"
                list_text += "\n"
                ul.replace_with(list_text)
            
            for ol in soup.find_all('ol'):
                items = ol.find_all('li')
                list_text = "\n"
                for i, item in enumerate(items, 1):
                    item_text = item.get_text(strip=True)
                    if item_text:
                        list_text += f"{i}. {item_text}\n"
                list_text += "\n"
                ol.replace_with(list_text)
            
            # 获取最终文本
            text = soup.get_text()
            
            # 清理文本
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line:
                    cleaned_lines.append(line)
            
            # 合并连续的空行
            final_text = '\n'.join(cleaned_lines)
            
            # 去除多余的空行
            final_text = re.sub(r'\n{3,}', '\n\n', final_text)
            
            return final_text.strip()
            
        except Exception as e:
            logger.error(f"转换HTML文件失败 {file_path}: {e}")
            return ""
    
    def _convert_pdf_to_text(self, file_path: str) -> str:
        """将PDF转换为文本"""
        try:
            doc = fitz.open(file_path)
            text = ""
            
            for page_num in range(doc.page_count):
                page = doc[page_num]
                page_text = page.get_text()
                if page_text.strip():
                    text += f"\n--- 第 {page_num + 1} 页 ---\n"
                    text += page_text
                    text += "\n"
            
            doc.close()
            
            # 清理文本
            text = re.sub(r'\n{3,}', '\n\n', text)
            return text.strip()
            
        except Exception as e:
            logger.error(f"转换PDF文件失败 {file_path}: {e}")
            return ""

# 港股文件下载器
class HKStockFilingsDownloader:
    """港股公告下载器"""
    def __init__(self):
        self.base_url = "https://www1.hkexnews.hk"
        self.prefix_url = f"{self.base_url}/search/prefix.do"
        self.search_url = f"{self.base_url}/search/titlesearch.xhtml"
        
        # 设置请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7,zh-CN;q=0.6,ja;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
        }
        
        # 文件类型映射
        self.filing_types = {
            'Annual Report': '年报',
            'Quarterly Results': '季报',
            'Interim Results': '中期报告',
            'Final Results': '全年业绩',
            'Financial Statements': '财务报表'
        }
        
    def get_stock_id(self, ticker):
        """根据股票代码获取股票ID"""
        # 清理股票代码，移除.HK后缀
        clean_ticker = clean_hk_ticker(ticker)
        
        # 构建请求URL
        timestamp = int(time.time() * 1000)
        params = {
            'callback': 'callback',
            'lang': 'EN',
            'type': 'A',
            'name': clean_ticker,
            'market': 'SEHK',
            '_': timestamp
        }
        
        # 设置AJAX请求头
        ajax_headers = self.headers.copy()
        ajax_headers.update({
            'Accept': 'text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Referer': f'{self.base_url}/search/titlesearch.xhtml?lang=en'
        })
        
        try:
            with httpx.Client(headers=ajax_headers, timeout=30) as client:
                response = client.get(self.prefix_url, params=params)
                response.raise_for_status()
                
                # 解析JSONP响应
                content = response.text
                logger.debug(f"港股API原始响应: {content}")
                
                # 移除JSONP包装
                data = None
                if content.startswith('callback(') and content.endswith(');'):
                    json_str = content[9:-2]
                    data = json.loads(json_str)
                elif content.startswith('callback(') and content.endswith('});'):
                    json_str = content[9:-3]
                    data = json.loads(json_str)
                else:
                    # 尝试用正则表达式提取JSON部分
                    match = re.search(r'callback\((.*)\);?\s*$', content)
                    if match:
                        json_str = match.group(1)
                        data = json.loads(json_str)
                    else:
                        logger.error(f"无法解析JSONP格式: {content}")
                        return None, None, None
                
                if 'stockInfo' in data and data['stockInfo']:
                    stock_info = data['stockInfo'][0]
                    stock_id = stock_info['stockId']
                    stock_code = stock_info['code']
                    stock_name = stock_info['name']
                    
                    logger.info(f"找到港股: {stock_code} - {stock_name} (ID: {stock_id})")
                    return stock_id, stock_code, stock_name
                else:
                    logger.warning(f"未找到港股代码 {ticker} 的信息")
                    return None, None, None
                    
        except Exception as e:
            logger.error(f"获取港股ID时出错: {str(e)}")
            return None, None, None
    
    def get_filings_list(self, stock_id, from_date=None, to_date=None, cutoff_date=None, status_callback=None):
        """获取指定股票的所有公告列表，支持自动翻页"""
        if not from_date:
            from_date = "19990401"  # 默认从1999年开始
        if not to_date:
            to_date = datetime.now().strftime("%Y%m%d")
        
        # 解析截止日期
        cutoff_datetime = None
        if cutoff_date:
            cutoff_datetime = datetime.strptime(cutoff_date, "%Y%m%d")
        
        all_filings = []
        row_range = 0  # 从第一页开始
        page_size = 100  # 每页100条记录
        total_record_count = None  # 总记录数
        
        while True:
            # 构建GET请求URL（第一页用POST，后续页面用GET）
            if row_range == 0:
                # 第一页使用POST请求
                post_data = {
                    'lang': 'EN',
                    'category': '0',
                    'market': 'SEHK',
                    'searchType': '0',
                    'documentType': '-1',
                    't1code': '-2',
                    't2Gcode': '-2',
                    't2code': '-2',
                    'stockId': str(stock_id),
                    'from': from_date,
                    'to': to_date,
                    'MB-Daterange': '0',
                    'title': ''
                }
                
                # 设置POST请求头
                post_headers = self.headers.copy()
                post_headers.update({
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Cache-Control': 'max-age=0',
                    'Referer': f'{self.base_url}/search/titlesearch.xhtml?lang=en'
                })
                
                try:
                    with httpx.Client(headers=post_headers, timeout=30) as client:
                        response = client.post(self.search_url, data=post_data)
                        response.raise_for_status()
                        
                        page_filings = self.parse_filings_html(response.text)
                        
                except Exception as e:
                    logger.error(f"获取港股公告列表第1页时出错: {str(e)}")
                    break
            else:
                # 后续页面使用GET请求
                get_url = f"{self.base_url}/search/titleSearchServlet.do"
                params = {
                    'sortDir': '0',
                    'sortByOptions': 'DateTime',
                    'category': '0',
                    'market': 'SEHK',
                    'stockId': str(stock_id),
                    'documentType': '-1',
                    'fromDate': from_date,
                    'toDate': to_date,
                    'title': '',
                    'searchType': '0',
                    't1code': '-2',
                    't2Gcode': '-2',
                    't2code': '-2',
                    'rowRange': str(row_range),
                    'lang': 'E'
                }
                
                # 设置GET请求头
                get_headers = self.headers.copy()
                get_headers.update({
                    'accept': '*/*',
                    'x-requested-with': 'XMLHttpRequest',
                    'Referer': f'{self.base_url}/search/titlesearch.xhtml?lang=en'
                })
                
                try:
                    with httpx.Client(headers=get_headers, timeout=30) as client:
                        response = client.get(get_url, params=params)
                        response.raise_for_status()
                        
                        # 解析JSON响应
                        json_data = response.json()
                        page_filings = self.parse_filings_json(json_data.get('result', '[]'))
                        
                        # 从JSON响应中获取总记录数
                        if total_record_count is None:
                            try:
                                import json
                                result_data = json.loads(json_data.get('result', '[]'))
                                if result_data and len(result_data) > 0:
                                    total_record_count = int(result_data[0].get('TOTAL_COUNT', 0))
                                    logger.info(f"港股公告总记录数: {total_record_count}")
                            except (json.JSONDecodeError, ValueError, KeyError) as e:
                                logger.warning(f"无法解析总记录数: {e}")
                        
                except Exception as e:
                    logger.error(f"获取港股公告列表第{row_range//page_size + 1}页时出错: {str(e)}")
                    break
            
            if not page_filings:
                logger.info(f"港股公告列表第{row_range//page_size + 1}页无数据，停止翻页")
                break
            
            # 先将本页所有公告添加到结果中
            all_filings.extend(page_filings)
            
            # 检查本页最后一个公告的日期是否早于截止日期
            if cutoff_datetime and page_filings:
                last_filing = page_filings[-1]  # 获取最后一个公告
                last_filing_date = self.parse_filing_date(last_filing.get('release_time', ''))
                if last_filing_date and last_filing_date < cutoff_datetime:
                    logger.info(f"港股公告最后一个日期 {last_filing_date} 早于截止日期 {cutoff_datetime}，停止翻页")
                    break
            
            # 如果这一页的记录数少于页面大小，说明已经是最后一页
            if len(page_filings) < page_size:
                logger.info(f"港股公告列表第{row_range//page_size + 1}页记录数 {len(page_filings)} 少于页面大小，停止翻页")
                break
            
            # 准备下一页
            row_range += page_size
            
            # 检查是否已经超过总记录数
            if total_record_count is not None and row_range >= total_record_count:
                logger.info(f"港股公告列表rowRange({row_range}) 已达到总记录数({total_record_count})，停止翻页")
                break
            
            logger.info(f"港股公告列表准备获取第{row_range//page_size + 1}页 (rowRange={row_range})")
            if status_callback:
                status_callback(f"正在获取第 {row_range//page_size + 1} 页港股公告...")
        
        logger.info(f"港股公告列表共获取 {len(all_filings)} 条记录")
        return all_filings
    
    def parse_filings_html(self, html_content):
        """解析HTML响应，提取公告链接"""
        soup = BeautifulSoup(html_content, 'html.parser')
        filings = []
        
        # 查找所有表格行
        table_rows = soup.find_all('tr')
        
        for row in table_rows:
            # 查找包含PDF链接的单元格
            doc_link_cell = row.find('div', class_='doc-link')
            if doc_link_cell:
                # 获取PDF链接
                pdf_link = doc_link_cell.find('a')
                if pdf_link and pdf_link.get('href'):
                    href = pdf_link.get('href')
                    
                    # 获取发布时间
                    time_cell = row.find('td', class_='release-time')
                    release_time = time_cell.get_text(strip=True).replace('Release Time: ', '') if time_cell else 'N/A'
                    
                    # 获取股票代码
                    code_cell = row.find('td', class_='stock-short-code')
                    stock_code = code_cell.get_text(strip=True).replace('Stock Code: ', '').split('\n')[0] if code_cell else 'N/A'
                    
                    # 获取股票名称
                    name_cell = row.find('td', class_='stock-short-name')
                    stock_name = name_cell.get_text(strip=True).replace('Stock Short Name: ', '').split('\n')[0] if name_cell else 'N/A'
                    
                    # 获取文档标题
                    doc_title = pdf_link.get_text(strip=True)
                    
                    # 获取文档类型（从headline div获取）
                    headline_div = row.find('div', class_='headline')
                    doc_type = headline_div.get_text(strip=True) if headline_div else 'Unknown'
                    
                    # 获取文件大小
                    filesize_span = doc_link_cell.find('span', class_='attachment_filesize')
                    filesize = filesize_span.get_text(strip=True) if filesize_span else 'N/A'
                    
                    # 构建完整URL
                    full_url = urljoin(self.base_url, href)
                    
                    filing_info = {
                        'release_time': release_time,
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'doc_type': doc_type,
                        'doc_title': doc_title,
                        'file_size': filesize,
                        'url': full_url,
                        'href': href
                    }
                    
                    filings.append(filing_info)
        
        return filings
    
    def parse_filings_json(self, json_string):
        """解析JSON格式的公告响应"""
        try:
            import json
            filings_data = json.loads(json_string)
            filings = []
            
            for item in filings_data:
                filing_info = {
                    'release_time': item.get('DATE_TIME', ''),
                    'stock_code': item.get('STOCK_CODE', '').replace('<br/>', '/'),
                    'stock_name': item.get('STOCK_NAME', '').replace('<br/>', '/'),
                    'doc_type': item.get('LONG_TEXT', ''),
                    'doc_title': item.get('TITLE', ''),
                    'file_size': item.get('FILE_INFO', ''),
                    'url': f"{self.base_url}{item.get('FILE_LINK', '')}",
                    'href': item.get('FILE_LINK', '')
                }
                filings.append(filing_info)
            
            return filings
            
        except Exception as e:
            logger.error(f"解析JSON公告数据失败: {e}")
            return []
    
    def parse_filing_date(self, date_str):
        """解析公告日期字符串为datetime对象"""
        try:
            # 港股日期格式：DD/MM/YYYY HH:MM
            if '/' in date_str and ' ' in date_str:
                date_part = date_str.split(' ')[0]  # 取日期部分
                parts = date_part.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    return datetime(int(year), int(month), int(day))
            return None
        except Exception as e:
            logger.warning(f"解析港股日期失败: {date_str} - {e}")
            return None
    
    def categorize_filings(self, filings):
        """将公告分为两组：季报年报组和其他组"""
        # 季报年报关键词（基于headline div内容）
        quarterly_annual_keywords = [
            'Final Results',
            'Quarterly Results', 
            'Interim Results',
            'Offer for Subscription'
        ]
        
        quarterly_annual_filings = []
        other_filings = []
        
        for filing in filings:
            doc_type = filing['doc_type']
            
            # 检查是否包含季报年报关键词
            is_quarterly_annual = any(keyword in doc_type for keyword in quarterly_annual_keywords)
            
            if is_quarterly_annual:
                quarterly_annual_filings.append(filing)
            else:
                other_filings.append(filing)
        
        return quarterly_annual_filings, other_filings
    
    def download_filing_content(self, filing_info):
        """下载单个公告文件内容"""
        try:
            with httpx.Client(headers=self.headers, timeout=60) as client:
                response = client.get(filing_info['url'])
                response.raise_for_status()
                
                return response.content
                
        except Exception as e:
            logger.error(f"下载港股文件时出错 {filing_info['url']}: {str(e)}")
            return None

# 装饰器
def retry_on_failure(max_retries: int = config.MAX_RETRIES, delay: float = config.RETRY_DELAY):
    """重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))  # 指数退避
            
            logger.error(f"函数 {func.__name__} 在 {max_retries} 次尝试后仍然失败")
            raise last_exception
        return wrapper
    return decorator

@contextmanager
def error_handler(operation_name: str):
    """错误处理上下文管理器"""
    try:
        yield
    except Exception as e:
        logger.error(f"{operation_name} 失败: {e}")
        st.error(f"{operation_name} 失败: {e}")
        raise

# Session State 管理
class SessionManager:
    """Session状态管理器"""
    
    @staticmethod
    def init_session_state():
        """初始化所有必要的session state变量"""
        
        # 添加回退机制：先检查 secrets.toml 文件是否存在，如果存在就使用 st.secrets，否则从环境变量读取
        def get_secret_value(key: str, default=None):
            """从 st.secrets 或环境变量中获取密钥值"""
            import os
            import json
            from pathlib import Path
            
            # 检查 secrets.toml 文件是否存在
            secrets_paths = [
                Path(".streamlit/secrets.toml"),
                Path("/root/.streamlit/secrets.toml"),
                Path("/app/.streamlit/secrets.toml")
            ]
            
            secrets_file_exists = any(path.exists() for path in secrets_paths)
            
            if secrets_file_exists:
                try:
                    return st.secrets[key]
                except KeyError:
                    # 如果 secrets.toml 存在但没有该键，回退到环境变量
                    pass
            
            # 直接从环境变量读取
            env_value = os.environ.get(key, default)
            if env_value is None:
                return default
                
            # 尝试解析 JSON 格式的环境变量（用于列表类型的密钥）
            if isinstance(env_value, str) and env_value.startswith('[') and env_value.endswith(']'):
                try:
                    return json.loads(env_value)
                except json.JSONDecodeError:
                    return env_value
            
            return env_value
        
        defaults = {
            "analyzer_messages": [],
            "analyzer_ticker": "",
            "analyzer_years": 1,
            "analyzer_use_sec_reports": True,
            "analyzer_use_sec_others": False,
            "analyzer_use_earnings": True,
            "analyzer_model": "gemini-2.5-flash",
            "api_key_cycle": cycle(get_secret_value("GOOGLE_API_KEYS", [])),
            "processing_status": ProcessingStatus().__dict__,
            "cache": {},
            "use_premium_api": False,
            "premium_access_code": "",
            "selected_language": "English",
            "analyzer_analysis_mode": "fast_mode"
        }
        
        for key, default_value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = default_value
    
    @staticmethod
    def get_processing_status() -> ProcessingStatus:
        """获取处理状态对象"""
        # Get the field names from the dataclass
        known_fields = {f.name for f in fields(ProcessingStatus)}
        # Filter the session state dict to only include known fields
        current_status_dict = st.session_state.get("processing_status", {})
        filtered_args = {k: v for k, v in current_status_dict.items() if k in known_fields}
        return ProcessingStatus(**filtered_args)
    
    @staticmethod
    def update_processing_status(status: ProcessingStatus):
        """更新处理状态"""
        st.session_state.processing_status = status.__dict__

# AI 服务
class GeminiService:
    """Gemini AI服务"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(max_calls=30, window=60)
    
    def get_next_api_key(self) -> str:
        """获取下一个API密钥"""
        # 檢查是否使用付費API
        if st.session_state.get("use_premium_api", False):
            return self._get_secret_value("PREMIUM_API_KEY")
        
        # 使用一般的輪換API
        if hasattr(st.session_state, 'api_key_cycle'):
            return next(st.session_state.api_key_cycle)
        else:
            # 如果session state未初始化，使用备用方案
            if not hasattr(self, '_api_key_cycle'):
                api_keys = self._get_secret_value("GOOGLE_API_KEYS", [])
                self._api_key_cycle = cycle(api_keys)
            return next(self._api_key_cycle)
    
    def _get_secret_value(self, key: str, default=None):
        """从 st.secrets 或环境变量中获取密钥值"""
        import os
        import json
        from pathlib import Path
        
        # 检查 secrets.toml 文件是否存在
        secrets_paths = [
            Path(".streamlit/secrets.toml"),
            Path("/root/.streamlit/secrets.toml"),
            Path("/app/.streamlit/secrets.toml")
        ]
        
        secrets_file_exists = any(path.exists() for path in secrets_paths)
        
        if secrets_file_exists:
            try:
                return st.secrets[key]
            except KeyError:
                # 如果 secrets.toml 存在但没有该键，回退到环境变量
                pass
        
        # 直接从环境变量读取
        env_value = os.environ.get(key, default)
        if env_value is None:
            return default
            
        # 尝试解析 JSON 格式的环境变量（用于列表类型的密钥）
        if isinstance(env_value, str) and env_value.startswith('[') and env_value.endswith(']'):
            try:
                return json.loads(env_value)
            except json.JSONDecodeError:
                return env_value
        
        return env_value
    
    def init_client(self) -> genai.Client:
        """初始化Gemini客户端"""
        return genai.Client(api_key=self.get_next_api_key())
    
    @retry_on_failure(max_retries=3)
    def call_api(self, prompt: str, model_type: str = "gemini-2.5-flash") -> str:
        """调用Gemini API"""
        self.rate_limiter.wait_if_needed()
        
        try:
            client = self.init_client()
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ]

            response = client.models.generate_content(
                model=model_type,
                contents=contents,
            )

            return response.candidates[0].content.parts[0].text
            
        except Exception as e:
            logger.error(f"Gemini API调用失败: {e}")
            raise APIError(f"Gemini API调用失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def call_api_stream(self, prompt: str, model_type: str = "gemini-2.5-flash"):
        """调用Gemini API 流式响应"""
        self.rate_limiter.wait_if_needed()
        
        try:
            client = self.init_client()
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ]

            # 使用流式响应
            response_stream = client.models.generate_content_stream(
                model=model_type,
                contents=contents,
            )
            
            # 生成器函数，逐步返回文本片段
            for chunk in response_stream:
                if chunk.candidates and chunk.candidates[0].content.parts:
                    yield chunk.candidates[0].content.parts[0].text
            
        except Exception as e:
            logger.error(f"Gemini API流式调用失败: {e}")
            raise APIError(f"Gemini API流式调用失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def classify_6k_document(self, document_content: str) -> bool:
        """使用便宜模型判断6-K文件是否为季报/年报/IPO报告"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            if language == "English":
                prompt = f"""
                You are a financial document classifier. Please analyze the following 6-K filing content and determine if it is a Quarterly Report, Annual Report, or IPO Report.

                Classification criteria:
                - Quarterly Report: Contains quarterly financial results, earnings data, quarterly business updates
                - Annual Report: Contains annual financial results, yearly business summary, annual shareholder information
                - IPO Report: Contains initial public offering information, prospectus data, listing announcements

                Please respond with ONLY a JSON object in this exact format:
                {{
                    "is_quarterly_annual_ipo": true/false,
                    "document_type": "quarterly/annual/ipo/other",
                    "confidence": "high/medium/low"
                }}

                Document content (first 5000 characters):
                {document_content[:5000]}
                """
            else:
                prompt = f"""
                你是一个金融文档分类器。请分析以下6-K文件内容，判断它是否是季报、年报或IPO报告。

                分类标准：
                - 季报：包含季度财务结果、盈利数据、季度业务更新
                - 年报：包含年度财务结果、年度业务总结、年度股东信息
                - IPO报告：包含首次公开发行信息、招股说明书数据、上市公告

                请只回答JSON格式：
                {{
                    "is_quarterly_annual_ipo": true/false,
                    "document_type": "quarterly/annual/ipo/other",
                    "confidence": "high/medium/low"
                }}

                文档内容（前5000字符）：
                {document_content[:5000]}
                """
            
            result = self.call_api(prompt, "gemini-2.5-flash-lite-preview-06-17")
            
            # 尝试解析JSON
            try:
                # 尝试从Markdown代码块中提取JSON
                import re
                match = re.search(r"```json\s*(\{.*?\})\s*```", result, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    json_str = result
                
                import json
                classification = json.loads(json_str)
                return classification.get("is_quarterly_annual_ipo", False)
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"解析6-K分类JSON失败: {e}. 模型返回: {result}")
                # 如果解析失败，保守处理，返回True继续分析
                return True
                
        except Exception as e:
            logger.error(f"6-K文档分类失败: {e}")
            # 如果分类失败，保守处理，返回True继续分析
            return True

# SEC 服务
class SECService:
    """SEC文件服务"""
    
    def __init__(self, cache_manager: CacheManager):
        self.rate_limiter = RateLimiter(max_calls=30, window=60)
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        self.cache_manager = cache_manager
        self.sixk_processor = None  # 将在需要时初始化
    
    def _init_sixk_processor(self, temp_dir: str):
        """初始化6-K处理器"""
        if self.sixk_processor is None:
            self.sixk_processor = SixKProcessor(temp_dir)

    @lru_cache(maxsize=100)
    def get_cik_map(self) -> Dict[str, str]:
        """获取ticker到CIK的映射（带缓存）"""
        cache_key = "cik_map"
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            headers = {'User-Agent': config.SEC_USER_AGENT}
            response = httpx.get(
                "https://www.sec.gov/files/company_tickers.json", 
                headers=headers,
                timeout=config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            all_companies = response.json()
            cik_map = {company['ticker']: company['cik_str'] for company in all_companies.values()}
            
            self.cache_manager.set(cache_key, cik_map)
            return cik_map
            
        except Exception as e:
            logger.error(f"获取CIK映射失败: {e}")
            raise DataRetrievalError(f"获取CIK映射失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def get_filings(self, ticker: str, years: int = 3, forms_to_include: Optional[List[str]] = None, status_callback=None) -> List[Document]:
        """获取SEC文件列表"""
        self.rate_limiter.wait_if_needed()
        
        # 如果未提供要包含的表单，则使用配置中的所有表单
        if forms_to_include is None:
            forms_to_include = config.SEC_FORMS
        
        cache_key = self.cache_manager.get_cache_key("sec_filings", ticker, years, tuple(sorted(forms_to_include)))
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            edgar = EdgarClient(user_agent=config.SEC_USER_AGENT)
            
            # 修正年份计算逻辑：如果是2年，就是2024/1/1到2025/1/1
            current_year = datetime.now().year
            end_date = datetime(current_year + 1, 1, 1)  # 延伸到下一年的1月1号
            start_date = datetime(current_year - years + 1, 1, 1)  # 往前推years年
            
            logger.info(f"SEC文件日期范围: {start_date.date()} 到 {end_date.date()}")
            
            ticker_map = self.get_cik_map()
            cik = ticker_map.get(ticker.upper())
            
            if not cik:
                logger.warning(f"未找到ticker {ticker} 的CIK")
                return []
            
            submissions = edgar.get_submissions(cik=str(cik).zfill(10))
            
            # 获取所有文件数据（包括recent和files）
            all_forms = []
            all_accession_numbers = []
            all_filing_dates = []
            all_primary_documents = []
            
            # 处理recent数据
            recent = submissions.get('filings', {}).get('recent', {})
            if recent and 'form' in recent:
                all_forms.extend(recent.get('form', []))
                all_accession_numbers.extend(recent.get('accessionNumber', []))
                all_filing_dates.extend(recent.get('filingDate', []))
                all_primary_documents.extend(recent.get('primaryDocument', []))
                logger.info(f"SEC recent文件数: {len(recent.get('form', []))}")
            
            # 处理files数据（历史文件）
            files = submissions.get('filings', {}).get('files', [])
            if files:
                logger.info(f"SEC需要处理 {len(files)} 个历史文件批次")
                max_batches = 100  # 最多处理10个批次，避免过多API调用
                processed_batches = 0
                
                for idx, file_info in enumerate(files):
                    if processed_batches >= max_batches:
                        logger.info(f"SEC已处理 {max_batches} 个批次，停止处理更多历史文件")
                        break
                        
                    file_name = file_info.get('name', '')
                    if file_name:
                        try:
                            if status_callback:
                                status_callback(f"正在获取第 {idx + 1}/{min(len(files), max_batches)} 批SEC历史文件...")
                            # 获取历史文件数据
                            historical_data = edgar.get_submissions(cik=str(cik).zfill(10), file_name=file_name)
                            if historical_data and 'form' in historical_data:
                                batch_size = len(historical_data.get('form', []))
                                logger.info(f"SEC历史文件批次 {file_name}: {batch_size} 个文件")
                                
                                # 检查批次中最早的日期，如果太早则停止
                                batch_dates = historical_data.get('filingDate', [])
                                if batch_dates:
                                    earliest_date = min(batch_dates)
                                    earliest_datetime = datetime.strptime(earliest_date, '%Y-%m-%d').date()
                                    if earliest_datetime < start_date.date():
                                        logger.info(f"SEC历史文件批次 {file_name} 最早日期 {earliest_datetime} 早于截止日期 {start_date.date()}，停止处理")
                                        break
                                
                                all_forms.extend(historical_data.get('form', []))
                                all_accession_numbers.extend(historical_data.get('accessionNumber', []))
                                all_filing_dates.extend(historical_data.get('filingDate', []))
                                all_primary_documents.extend(historical_data.get('primaryDocument', []))
                                processed_batches += 1
                        except Exception as e:
                            logger.warning(f"获取SEC历史文件批次 {file_name} 失败: {e}")
                            continue
            
            if not all_forms:
                logger.warning(f"未找到SEC文件数据")
                return []
            
            logger.info(f"SEC总文件数: {len(all_forms)}")
            
            documents = []
            cutoff_reached = False
            
            for i in range(len(all_forms)):
                form_type = all_forms[i]
                if form_type in forms_to_include:
                    filing_date = datetime.strptime(all_filing_dates[i], '%Y-%m-%d').date()
                    
                    # 检查是否早于截止日期
                    if filing_date < start_date.date():
                        logger.info(f"SEC文件日期 {filing_date} 早于截止日期 {start_date.date()}，停止处理")
                        cutoff_reached = True
                        break
                    
                    if start_date.date() <= filing_date < end_date.date():  # 不包含结束日期
                        accession_no_no_dashes = all_accession_numbers[i].replace('-', '')
                        filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_no_dashes}/{all_primary_documents[i]}"
                        
                        documents.append(Document(
                            type='SEC Filing',
                            title=f"{ticker} {form_type}",
                            date=filing_date,
                            url=filing_url,
                            form_type=form_type
                        ))
            
            # 按日期排序（新到旧）
            documents.sort(key=lambda x: x.date, reverse=True)
            
            logger.info(f"找到 {len(documents)} 个SEC文件")
            self.cache_manager.set(cache_key, documents)
            return documents
            
        except Exception as e:
            logger.error(f"获取SEC文件失败: {e}")
            raise DataRetrievalError(f"获取SEC文件失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def download_filing(self, filing_url: str) -> str:
        """下载SEC文件内容"""
        self.rate_limiter.wait_if_needed()
        
        try:
            response = httpx.get(
                filing_url, 
                headers={"User-Agent": config.SEC_USER_AGENT},
                timeout=config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            document_tag = soup.find('document')
            
            content = document_tag.get_text(separator='\n', strip=True) if document_tag else soup.get_text(separator='\n', strip=True)
            
            # 限制内容长度
            if len(content) > config.MAX_CONTENT_LENGTH:
                content = content[:config.MAX_CONTENT_LENGTH] + "\n[内容已截断]"
            
            return content
            
        except Exception as e:
            logger.error(f"下载SEC文件失败: {e}")
            return f"下载文件时出错: {e}"

# 港股服务
class HKStockService:
    """港股文件服务"""
    
    def __init__(self, cache_manager: CacheManager):
        self.rate_limiter = RateLimiter(max_calls=30, window=60)
        self.cache_manager = cache_manager
        self.downloader = HKStockFilingsDownloader()
    
    def parse_hk_date(self, date_str: str) -> Optional[datetime.date]:
        """解析港股日期格式"""
        try:
            # 港股日期格式：DD/MM/YYYY HH:MM 或 Release Time:DD/MM/YYYY HH:MM
            date_part = date_str
            if 'Release Time:' in date_str:
                date_part = date_str.replace('Release Time:', '').strip()
            
            if '/' in date_part and ' ' in date_part:
                date_only = date_part.split(' ')[0]  # 取日期部分
                parts = date_only.split('/')
                if len(parts) == 3:
                    day, month, year = parts
                    return datetime(int(year), int(month), int(day)).date()
            return None
        except Exception as e:
            logger.warning(f"解析港股日期失败: {date_str} - {e}")
            return None
    
    @retry_on_failure(max_retries=3)
    def get_hk_filings(self, ticker: str, years: int = 3, forms_to_include: Optional[List[str]] = None, status_callback=None) -> List[Document]:
        """获取港股文件列表"""
        self.rate_limiter.wait_if_needed()
        
        # 如果未提供要包含的表单，则使用默认的季报年报
        if forms_to_include is None:
            forms_to_include = ['quarterly_annual']
        
        cache_key = self.cache_manager.get_cache_key("hk_filings", ticker, years, tuple(sorted(forms_to_include)))
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # 获取股票ID
            if status_callback:
                status_callback("正在获取港股ID...")
            stock_id, stock_code, stock_name = self.downloader.get_stock_id(ticker)
            if not stock_id:
                logger.warning(f"未找到港股ticker {ticker} 的信息")
                return []
            
            # 计算日期范围
            current_year = datetime.now().year
            end_date = datetime(current_year + 1, 1, 1)
            start_date = datetime(current_year - years + 1, 1, 1)
            
            # 转换为港股API格式
            from_date = start_date.strftime("%Y%m%d")
            to_date = end_date.strftime("%Y%m%d")
            
            logger.info(f"港股文件日期范围: {start_date.date()} 到 {end_date.date()}")
            
            # 获取公告列表
            if status_callback:
                status_callback("正在获取港股公告列表...")
            all_filings = self.downloader.get_filings_list(stock_id, from_date, to_date, from_date, status_callback)
            
            if not all_filings:
                logger.warning(f"未找到港股 {ticker} 的公告")
                return []
            
            # 分类公告
            quarterly_annual_filings, other_filings = self.downloader.categorize_filings(all_filings)
            
            # 根据用户选择决定使用哪些公告
            selected_filings = []
            if 'quarterly_annual' in forms_to_include:
                selected_filings.extend(quarterly_annual_filings)
            if 'others' in forms_to_include:
                selected_filings.extend(other_filings)
            
            # 转换为Document对象
            documents = []
            for filing in selected_filings:
                # 解析日期
                filing_date = self.parse_hk_date(filing['release_time'])
                if filing_date and start_date.date() <= filing_date < end_date.date():
                    documents.append(Document(
                        type='HK Stock Filing',
                        title=f"{stock_code} {filing['doc_type']} - {filing['doc_title']}",
                        date=filing_date,
                        url=filing['url'],
                        form_type=filing['doc_type'],
                        content=None  # 内容将在需要时下载
                    ))
            
            # 按日期排序（新到旧）
            documents.sort(key=lambda x: x.date, reverse=True)
            
            logger.info(f"找到 {len(documents)} 个港股文件")
            self.cache_manager.set(cache_key, documents)
            return documents
            
        except Exception as e:
            logger.error(f"获取港股文件失败: {e}")
            raise DataRetrievalError(f"获取港股文件失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def download_hk_filing(self, filing_url: str) -> str:
        """下载港股文件内容"""
        self.rate_limiter.wait_if_needed()
        
        try:
            # 构建filing_info对象
            filing_info = {'url': filing_url}
            
            # 下载PDF内容
            pdf_content = self.downloader.download_filing_content(filing_info)
            
            if not pdf_content:
                return "下载港股文件失败"
            
            # 使用PyMuPDF处理PDF
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(pdf_content)
                temp_file_path = temp_file.name
            
            try:
                # 使用PyMuPDF提取文本
                doc = fitz.open(temp_file_path)
                text = ""
                
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    page_text = page.get_text()
                    if page_text.strip():
                        text += f"\n--- 第 {page_num + 1} 页 ---\n"
                        text += page_text
                        text += "\n"
                
                doc.close()
                
                # 清理文本
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                # 限制内容长度
                if len(text) > config.MAX_CONTENT_LENGTH:
                    text = text[:config.MAX_CONTENT_LENGTH] + "\n[内容已截断]"
                
                return text.strip()
                
            finally:
                # 清理临时文件
                os.unlink(temp_file_path)
            
        except Exception as e:
            logger.error(f"下载港股文件失败: {e}")
            return f"下载港股文件时出错: {e}"

# 沙特交易所服务
class SaudiExchangeService:
    """沙特交易所公告服务"""
    
    def __init__(self, cache_manager: CacheManager):
        self.rate_limiter = RateLimiter(max_calls=30, window=60)
        self.cache_manager = cache_manager
        self.session = requests.Session()
        self.base_url = "https://www.saudiexchange.sa"
        self.announcement_api = "https://www.saudiexchange.sa/wps/portal/saudiexchange/newsandreports/issuer-news/issuer-announcements/!ut/p/z1/lY_NDoIwHMOfhQcwqxD-zOPUODAgTBjiLmYHY0h0ejA-v8Qb-BHsrcmvacsMa5hx9tGe7L29Onvu_N7QIRQEP-bIEVcLEEpJuuLTpU9s1wd4JglqI1TuRyFkDWb-yqMsQqhVkQUptpCgcXl8kRjRb_pILmZRt2A9l0kqAk7REPhwcVDy_uEF_BhZHh27XbRu0CYT4XlP_MzK5g!!/p0/IZ7_5A602H80O0HTC060SG6UT81DI1=CZ6_5A602H80O0HTC060SG6UT81D26=NJgetAnnouncementListData=/"
        
        # 设置请求头
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest",
            "referer": "https://www.saudiexchange.sa/wps/portal/saudiexchange/newsandreports/issuer-news/issuer-announcements?locale=en&page=1",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
    
    def parse_saudi_date(self, date_str: str) -> Optional[datetime.date]:
        """解析沙特交易所日期格式: 27/05/2025 15:51:58 (dd/MM/yyyy HH:mm:ss)"""
        try:
            # 格式: dd/MM/yyyy HH:mm:ss
            dt = datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S')
            return dt.date()
        except Exception as e:
            logger.warning(f"解析沙特日期失败: {date_str}, 错误: {e}")
            return None
    
    @retry_on_failure(max_retries=3)
    def get_saudi_filings(self, symbol: str, years: int = 3, status_callback=None) -> List[Document]:
        """获取沙特交易所公告列表"""
        self.rate_limiter.wait_if_needed()
        
        cache_key = self.cache_manager.get_cache_key("saudi_filings", symbol, years)
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            # 计算日期范围
            current_date = datetime.now()
            cutoff_date = current_date - timedelta(days=years * 365)
            
            logger.info(f"获取沙特交易所 {symbol} 公告，日期范围: {cutoff_date.date()} 到 {current_date.date()}")
            
            all_documents = []
            page = 1
            page_size = 50  # 每页获取更多数据
            
            while True:
                if status_callback:
                    status_callback(f"正在获取第 {page} 页公告...")
                
                # 构建请求数据
                post_data = {
                    "annoucmentType": "1_-1",
                    "symbol": symbol,
                    "sectorDpId": "",
                    "searchType": "",
                    "fromDate": "",
                    "toDate": "",
                    "datePeriod": "",
                    "productType": "",
                    "advisorsList": "",
                    "textSearch": "",
                    "pageNumberDb": str(page),
                    "pageSize": str(page_size)
                }
                
                logger.info(f"🔍 [SAUDI] 请求第 {page} 页，symbol: {symbol}")
                
                response = self.session.post(
                    self.announcement_api,
                    data=post_data,
                    headers=self.headers,
                    timeout=30
                )
                response.raise_for_status()
                
                # 解析响应
                try:
                    data = response.json()
                    logger.info(f"🔍 [SAUDI] 第 {page} 页响应成功，数据类型: {type(data)}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}")
                    logger.error(f"响应内容: {response.text[:500]}")
                    break
                
                # 检查是否有公告数据
                announcements = data.get('announcementList', [])
                total_count = data.get('totalCount', 0)
                
                logger.info(f"🔍 [SAUDI] 第 {page} 页找到 {len(announcements)} 个公告，总数: {total_count}")
                
                if not announcements:
                    logger.info(f"第 {page} 页没有公告，停止获取")
                    break
                
                # 处理当前页的公告
                page_documents = []
                for announcement in announcements:
                    try:
                        # 解析日期
                        date_str = announcement.get('newsDateStr', '')
                        filing_date = self.parse_saudi_date(date_str)
                        
                        if not filing_date:
                            logger.warning(f"跳过日期解析失败的公告: {date_str}")
                            continue
                        
                        # 检查日期是否在范围内
                        if filing_date < cutoff_date.date():
                            logger.info(f"公告日期 {filing_date} 早于截止日期 {cutoff_date.date()}，停止处理")
                            # 先将当前页已处理的文档添加到all_documents，然后停止
                            if page_documents:
                                logger.info(f"🔍 [SAUDI] 停止前添加当前页文档: {len(page_documents)} 个")
                                all_documents.extend(page_documents)
                                logger.info(f"🔍 [SAUDI] 停止前all_documents长度: {len(all_documents)}")
                            return all_documents
                        
                        # 获取公告URL
                        announcement_url = announcement.get('announcementUrl', '')
                        if not announcement_url:
                            logger.warning("公告URL为空，跳过")
                            continue
                        
                        # 构建完整URL
                        if not announcement_url.startswith('http'):
                            announcement_url = urljoin(self.base_url, announcement_url)
                        
                        # 创建文档对象
                        raw_title = announcement.get('announcementTitle', '').strip()
                        if not raw_title:
                            title = f"{symbol} Announcement"
                        elif raw_title.startswith(symbol):
                            title = raw_title  # 如果标题已经包含symbol，直接使用
                        else:
                            title = f"{symbol} - {raw_title}"  # 否则添加前缀
                        
                        document = Document(
                            type='Saudi Exchange Filing',
                            title=title,
                            date=filing_date,
                            url=announcement_url,
                            form_type="Saudi Announcement"
                        )
                        
                        page_documents.append(document)
                        logger.info(f"✅ [SAUDI] 添加公告: {title}, 日期: {filing_date}")
                        
                    except Exception as e:
                        logger.warning(f"处理公告失败: {e}")
                        continue
                
                logger.info(f"🔍 [SAUDI] 第{page}页处理完成: page_documents长度={len(page_documents)}")
                all_documents.extend(page_documents)
                logger.info(f"🔍 [SAUDI] extend后: all_documents长度={len(all_documents)}")
                
                # 检查是否需要继续翻页
                if len(announcements) < page_size:
                    logger.info(f"第 {page} 页公告数量 {len(announcements)} 小于页面大小 {page_size}，停止翻页")
                    break
                
                page += 1
                
                # 防止无限循环
                if page > 100:
                    logger.warning("已获取100页，停止翻页")
                    break
                
                # 短暂延迟避免请求过快
                time.sleep(0.5)
            
            # 按日期排序（新到旧）
            all_documents.sort(key=lambda x: x.date, reverse=True)
            
            logger.info(f"✅ [SAUDI] 共获取 {len(all_documents)} 个沙特交易所公告")
            logger.info(f"🔍 [SAUDI] 返回前调试: all_documents类型={type(all_documents)}, 长度={len(all_documents)}")
            if all_documents:
                for i, doc in enumerate(all_documents[:3]):  # 只显示前3个
                    logger.info(f"🔍 [SAUDI] all_documents[{i}]: {doc.title}, 类型={doc.type}, 日期={doc.date}")
            
            # 缓存结果
            self.cache_manager.set(cache_key, all_documents)
            return all_documents
            
        except Exception as e:
            logger.error(f"获取沙特交易所公告失败: {e}")
            raise DataRetrievalError(f"获取沙特交易所公告失败: {e}")
    
    @retry_on_failure(max_retries=3)
    def download_saudi_filing(self, filing_url: str) -> str:
        """下载沙特交易所公告内容，包括PDF附件"""
        self.rate_limiter.wait_if_needed()
        
        try:
            logger.info(f"🔍 [SAUDI] 开始下载公告内容: {filing_url}")
            
            # 首先获取HTML页面
            response = self.session.get(filing_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 提取主要内容
            content = ""
            
            # 使用 newspaper3k 提取文章内容
            try:
                article = Article(filing_url)
                article.download()
                article.parse()
                main_content = article.text
                
                if main_content and len(main_content.strip()) > 50:
                    content += "=== 公告主要内容 ===\n"
                    content += main_content.strip()
                    content += "\n\n"
            except Exception as e:
                logger.warning(f"newspaper3k 提取失败: {e}")
            
            # 如果主要内容为空，尝试直接解析HTML
            if not content:
                # 移除脚本和样式
                for script in soup(["script", "style"]):
                    script.decompose()
                
                main_content = soup.get_text(separator='\n', strip=True)
                if main_content:
                    content += "=== 公告主要内容 ===\n"
                    content += main_content
                    content += "\n\n"
            
            # 检查PDF附件
            pdf_attachments = self._extract_pdf_attachments(soup, filing_url)
            
            if pdf_attachments:
                logger.info(f"🔍 [SAUDI-PDF] 发现 {len(pdf_attachments)} 个PDF附件")
                
                for i, pdf_info in enumerate(pdf_attachments):
                    try:
                        pdf_content = self._download_and_extract_pdf(pdf_info['url'], pdf_info['filename'])
                        if pdf_content:
                            content += f"=== PDF附件 {i+1}: {pdf_info['filename']} ===\n"
                            content += pdf_content
                            content += "\n\n"
                            logger.info(f"✅ [SAUDI-PDF] 成功提取PDF内容: {pdf_info['filename']}")
                        else:
                            logger.warning(f"❌ [SAUDI-PDF] PDF内容提取失败: {pdf_info['filename']}")
                    except Exception as e:
                        logger.error(f"❌ [SAUDI-PDF] 处理PDF附件失败: {pdf_info['filename']} - {e}")
                        content += f"=== PDF附件 {i+1}: {pdf_info['filename']} (处理失败) ===\n"
                        content += f"PDF处理失败: {str(e)}\n\n"
            
            # 限制内容长度
            if len(content) > config.MAX_CONTENT_LENGTH:
                content = content[:config.MAX_CONTENT_LENGTH] + "\n[内容已截断]"
            
            logger.info(f"✅ [SAUDI] 成功提取内容，长度: {len(content)}")
            return content.strip() if content.strip() else "未能提取到内容"
            
        except Exception as e:
            logger.error(f"下载沙特交易所公告失败: {e}")
            return f"下载失败: {str(e)}"
    
    def download_saudi_filings_batch(self, documents: List[Document], max_workers: int = 5, status_callback=None) -> List[Document]:
        """批量并发下载沙特交易所公告内容"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import streamlit as st
        
        def download_single_filing(doc_with_index):
            index, document = doc_with_index
            try:
                content = self.download_saudi_filing(document.url)
                document.content = content
                logger.info(f"✅ [SAUDI-BATCH] 完成下载 {index+1}/{len(saudi_docs)}: {document.title[:50]}...")
                return index, document
            except Exception as e:
                logger.error(f"❌ [SAUDI-BATCH] 下载失败 {index+1}/{len(saudi_docs)}: {document.title[:50]}... - {e}")
                document.content = f"下载失败: {str(e)}"
                return index, document
        
        # 过滤出需要下载内容的沙特文档
        saudi_docs = [doc for doc in documents if doc.type == 'Saudi Exchange Filing' and not doc.content]
        
        if not saudi_docs:
            logger.info("🔍 [SAUDI-BATCH] 没有需要下载的沙特文档")
            return documents
        
        logger.info(f"🚀 [SAUDI-BATCH] 开始批量下载 {len(saudi_docs)} 个沙特公告，并发数: {max_workers}")
        
        # 使用线程池并发下载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_index = {
                executor.submit(download_single_filing, (i, doc)): i 
                for i, doc in enumerate(saudi_docs)
            }
            
            completed_count = 0
            results = {}
            
            # 初始化状态显示
            if status_callback:
                status_callback("🚀 开始批量下载沙特交易所公告...", 0, len(saudi_docs))
            
            for future in as_completed(future_to_index):
                completed_count += 1
                try:
                    index, result_doc = future.result()
                    results[index] = result_doc
                    logger.info(f"📊 [SAUDI-BATCH] 进度: {completed_count}/{len(saudi_docs)} 完成")
                    
                    # 在主线程中更新状态
                    if status_callback:
                        progress_percent = (completed_count / len(saudi_docs)) * 100
                        status_callback(f"📊 Downloading: {completed_count}/{len(saudi_docs)} ({progress_percent:.0f}%)", completed_count, len(saudi_docs))
                        
                except Exception as e:
                    logger.error(f"❌ [SAUDI-BATCH] 任务执行失败: {e}")
        
        # 最终状态更新
        if status_callback:
            status_callback(f"🎉 批量下载完成! 共 {len(saudi_docs)} 个文档", len(saudi_docs), len(saudi_docs))
        
        logger.info(f"🎉 [SAUDI-BATCH] 批量下载完成! 总计: {len(saudi_docs)} 个文档")
        return documents
    
    def _extract_pdf_attachments(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """从HTML页面提取PDF附件链接"""
        pdf_attachments = []
        
        try:
            # 查找所有tr元素
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                
                # 检查是否有至少两个td，且第一个td包含"Attached Documents"
                if len(tds) >= 2:
                    first_td = tds[0].get_text(strip=True)
                    if "Attached Documents" in first_td:
                        # 检查第二个td中是否有PDF链接
                        second_td = tds[1]
                        pdf_links = second_td.find_all('a', href=True)
                        
                        for link in pdf_links:
                            href = link['href']
                            if href.endswith('.pdf'):
                                # 构建完整URL
                                if href.startswith('/'):
                                    full_url = urljoin(self.base_url, href)
                                else:
                                    full_url = urljoin(base_url, href)
                                
                                # 提取文件名
                                filename = href.split('/')[-1]
                                
                                pdf_attachments.append({
                                    'url': full_url,
                                    'filename': filename,
                                    'original_href': href
                                })
                                
                                logger.info(f"🔍 [SAUDI-PDF] 发现PDF附件: {filename} -> {full_url}")
            
            return pdf_attachments
            
        except Exception as e:
            logger.error(f"提取PDF附件失败: {e}")
            return []
    
    def _download_and_extract_pdf(self, pdf_url: str, filename: str) -> str:
        """下载PDF文件并提取文本内容"""
        import tempfile
        import os
        import fitz  # PyMuPDF
        
        try:
            logger.info(f"🔍 [SAUDI-PDF] 开始下载PDF: {filename}")
            
            # 下载PDF文件
            response = self.session.get(pdf_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            
            try:
                # 使用PyMuPDF提取文本
                doc = fitz.open(temp_file_path)
                text = ""
                
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    page_text = page.get_text()
                    if page_text.strip():
                        text += f"\n--- 第 {page_num + 1} 页 ---\n"
                        text += page_text
                        text += "\n"
                
                doc.close()
                
                # 清理文本
                import re
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                logger.info(f"✅ [SAUDI-PDF] PDF文本提取成功: {filename}, 长度: {len(text)}")
                return text.strip()
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"下载或提取PDF失败 {filename}: {e}")
            return ""

# 财报会议记录服务
class EarningsService:
    """财报会议记录服务"""
    
    def __init__(self, cache_manager: CacheManager):
        self.rate_limiter = RateLimiter(max_calls=30, window=60)
        self.cache_manager = cache_manager
        self.session = requests.Session() # 使用持久化会话处理cookies
        self._lock = threading.Lock()  # 添加线程锁用于并行处理

    @staticmethod
    def parse_transcript_url(url_path: str) -> Optional[Tuple[str, int, str]]:
        """
        从URL路径中解析股票代码、年份和季度信息
        
        Args:
            url_path (str): transcript URL路径, 例如 '/company/BABA/transcripts/2025/4/'
        
        Returns:
            tuple: (ticker, year, quarter) 或 None
        """
        # 允许ticker中包含点(.)和数字
        pattern = r'/company/([A-Z0-9\.]+)/transcripts/(\d{4})/(\d+)/'
        match = re.match(pattern, url_path)
        
        if match:
            ticker, year, quarter = match.groups()
            return ticker, int(year), str(quarter)
        
        return None

    def get_earnings_transcript_batch(self, url_paths: List[str], max_workers: int = 1) -> List[Optional[Dict]]:
        """
        并行获取多个财报会议记录
        
        Args:
            url_paths: URL路径列表
            max_workers: 最大并行工作线程数
        
        Returns:
            List[Optional[Dict]]: 财报记录信息列表，与输入顺序一致
        """
        results = [None] * len(url_paths)  # 预分配结果列表
        
        def process_single_transcript(index_url_pair):
            """处理单个财报记录的内部函数"""
            index, url_path = index_url_pair
            try:
                with self._lock:
                    # 使用锁来限制并发请求
                    self.rate_limiter.wait_if_needed()
                
                result = self.get_earnings_transcript(url_path)
                return index, result
            except Exception as e:
                logger.error(f"并行处理财报记录失败 {url_path}: {e}")
                return index, None
        
        # 使用ThreadPoolExecutor进行并行处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(process_single_transcript, (i, url_path)): i 
                for i, url_path in enumerate(url_paths)
            }
            
            # 收集结果
            for future in as_completed(future_to_index):
                try:
                    index, result = future.result()
                    results[index] = result
                except Exception as e:
                    index = future_to_index[future]
                    logger.error(f"并行处理任务失败 index {index}: {e}")
                    results[index] = None
        
        return results

    @retry_on_failure(max_retries=3)
    def get_available_quarters(self, ticker: str) -> List[str]:
        """获取指定公司所有可用的季度URL列表 (与测试脚本对齐)"""
        self.rate_limiter.wait_if_needed()
        
        cache_key = self.cache_manager.get_cache_key("earnings_quarters_urls", ticker)
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            logger.info(f"从缓存加载 {ticker} 的可用季度列表")
            return cached_result
        
        try:
            ticker_upper = ticker.upper()
            logger.info(f"获取 {ticker_upper} 的所有可用季度...")
            url = f"https://discountingcashflows.com/company/{ticker_upper}/transcripts/?org.htmx.cache-buster=baseContent"
            headers = {
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7,zh-CN;q=0.6,ja;q=0.5",
                "hx-boosted": "true",
                "hx-current-url": f"https://discountingcashflows.com/company/{ticker_upper}/chart/",
                "hx-request": "true",
                "hx-target": "baseContent",
                "priority": "u=1, i",
                "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            }
            
            response = self.session.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
            logger.info(f"获取可用季度列表 响应状态码: {response.status_code}")
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            transcript_links = []
            
            pattern = re.compile(rf'/company/{ticker_upper}/transcripts/(\d{{4}})/(\d+)/')
            
            for link in soup.find_all('a', href=pattern):
                href = link.get('href')
                if href and href != f'/company/{ticker_upper}/transcripts/':
                    transcript_links.append(href)
            
            transcript_links = sorted(list(set(transcript_links)), reverse=True)
            logger.info(f"找到 {len(transcript_links)} 个可用季度 for {ticker_upper}")
            
            self.cache_manager.set(cache_key, transcript_links)
            return transcript_links
            
        except Exception as e:
            logger.error(f"获取财报会议记录季度列表失败: {e}")
            raise DataRetrievalError(f"获取财报会议记录季度列表失败: {e}")
    
    def parse_date_text(self, date_text: str) -> Optional[datetime.date]:
        """解析日期文本"""
        if not date_text:
            return None
        
        for fmt in config.DATE_FORMATS:
            try:
                return datetime.strptime(date_text, fmt).date()
            except ValueError:
                continue
        
        logger.warning(f"无法解析日期格式: {date_text}")
        return None
    
    @retry_on_failure(max_retries=3)
    def get_earnings_transcript(self, url_path: str) -> Optional[Dict]:
        """
        获取单个财报会议记录，包含日期解析和文件保存，与测试脚本逻辑完全对齐。
        """
        self.rate_limiter.wait_if_needed()

        parsed_info = self.parse_transcript_url(url_path)
        if not parsed_info:
            logger.error(f"无法从URL路径解析信息: {url_path}")
            return None
        ticker, year, quarter_num = parsed_info
        logger.info(f"--- 开始获取: {ticker} Q{quarter_num} {year} ---")
        logger.info(f"选择的URL: {url_path}")

        try:
            base_url = f"https://discountingcashflows.com{url_path}"
            cache_buster_url = f"{base_url}?org.htmx.cache-buster=transcriptsContent"
            
            headers = {
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7,zh-CN;q=0.6,ja;q=0.5",
                "hx-boosted": "true",
                "hx-current-url": base_url,
                "hx-request": "true",
                "hx-target": "transcriptsContent",
                "priority": "u=1, i",
                "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
            }

            logger.info(f"Getting main page: {base_url}")
            main_response = self.session.get(base_url, headers={"User-Agent": headers["User-Agent"]})
            logger.info(f"Main page response status: {main_response.status_code}")
            main_response.raise_for_status()

            csrf_match = re.search(r'csrftoken["\']?\s*:\s*["\']([^"\']+)["\']', main_response.text)
            if not csrf_match:
                csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']', main_response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
                headers["x-csrftoken"] = csrf_token
                self.session.cookies['csrftoken'] = csrf_token
                logger.info(f"Extracted CSRF token: {csrf_token[:20]}...")

            logger.info(f"Making transcript request: {cache_buster_url}")
            response = self.session.get(cache_buster_url, headers=headers, timeout=config.REQUEST_TIMEOUT)
            logger.info(f"Transcript response status code: {response.status_code}")
            response.raise_for_status()
            
            transcript_data, fiscal_info = self._parse_html_transcript(response.text)
            
            if transcript_data:
                # 解析日期
                parsed_date = self.parse_date_text(fiscal_info.get('date'))

                # 保存文件 (可选)
                txt_filename = None
                html_filename = None
                if SAVE_TRANSCRIPT_FILES:
                    txt_filename = self._save_transcript_as_txt(
                        transcript_data,
                        fiscal_info,
                        f"transcript_{ticker}_FY{fiscal_info.get('fiscal_year', year)}_Q{quarter_num}.txt"
                    )
                    html_filename = self._save_raw_html(response.text, ticker, fiscal_info, quarter_num)
                
                # 返回结构化数据
                return {
                    'ticker': ticker,
                    'year': year,
                    'quarter': quarter_num,
                    'date': parsed_date,
                    'content': transcript_data.get('content', ''),
                    'txt_filename': txt_filename,
                    'html_filename': html_filename,
                    'parsed_successfully': True
                }
            else:
                logger.error(f"未能从HTML解析财报数据: {url_path}")
                return None
            
        except Exception as e:
            logger.error(f"获取财报会议记录时出错: {e} from {url_path}")
            raise DataRetrievalError(f"获取财报会议记录时出错: {e}")

    def _parse_html_transcript(self, html_content: str) -> Tuple[Optional[Dict], Dict]:
        """从HTML内容中解析结构化数据"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            fiscal_info = {}
            
            # 查找财年信息
            fiscal_span = soup.find('span', string=re.compile(r'Fiscal Year.*Quarter'))
            if fiscal_span:
                fiscal_text = fiscal_span.get_text()
                fy_match = re.search(r'Fiscal Year \(FY\) (\d+), Quarter (\d+)', fiscal_text)
                if fy_match:
                    fiscal_info['fiscal_year'] = fy_match.group(1)
                    fiscal_info['quarter'] = fy_match.group(2)
            
            # 查找日期信息
            date_span = soup.find('span', class_='text-xs')
            if date_span:
                date_text = date_span.get_text().strip()
                fiscal_info['date'] = date_text
            
            # 从textarea中提取内容
            textarea = soup.find('textarea', id='AIInsightsContent')
            if not textarea:
                return None, fiscal_info
            
            json_content = html.unescape(textarea.get_text())
            transcript_data = json.loads(json_content)
            return transcript_data, fiscal_info
            
        except Exception as e:
            logger.error(f"解析HTML时出错: {e}")
            return None, {}

    def _extract_speaker_content(self, transcript_content: str) -> List[Dict]:
        """从记录中提取发言人和内容"""
        speakers_content = []
        lines = transcript_content.split('\n')
        current_speaker = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            speaker_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[-:](.*)$', line)
            if speaker_match:
                if current_speaker and current_content:
                    speakers_content.append({
                        'speaker': current_speaker,
                        'content': ' '.join(current_content).strip()
                    })
                current_speaker = speaker_match.group(1).strip()
                current_content = [speaker_match.group(2).strip()] if speaker_match.group(2).strip() else []
            else:
                if current_speaker:
                    current_content.append(line)
        
        if current_speaker and current_content:
            speakers_content.append({
                'speaker': current_speaker,
                'content': ' '.join(current_content).strip()
            })
        return speakers_content

    def _save_raw_html(self, html_content: str, ticker: str, fiscal_info: Dict, quarter_num: str) -> Optional[str]:
        """保存原始HTML文件"""
        try:
            folder_name = f"{ticker}_transcripts"
            os.makedirs(folder_name, exist_ok=True)
            html_filename = f"{folder_name}/transcript_{ticker}_FY{fiscal_info.get('fiscal_year', 'UNKNOWN')}_Q{quarter_num}.html"
            with open(html_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"原始HTML已保存到: {html_filename}")
            return html_filename
        except Exception as e:
            logger.error(f"保存HTML文件时发生错误: {e}")
            return None

    def _save_transcript_as_txt(self, transcript_data: Dict, fiscal_info: Dict, filename: str) -> Optional[str]:
        """将解析后的记录保存为TXT文件"""
        try:
            ticker = transcript_data.get('symbol', 'UNKNOWN')
            folder_name = f"{ticker}_transcripts"
            os.makedirs(folder_name, exist_ok=True)
            txt_filename = f"{folder_name}/{filename}"
            
            with open(txt_filename, 'w', encoding='utf-8') as f:
                f.write("="*60 + "\nEARNINGS CALL TRANSCRIPT\n" + "="*60 + "\n\n")
                if fiscal_info:
                    f.write(f"Company: {transcript_data.get('symbol', 'N/A')}\n")
                    f.write(f"Fiscal Year: {fiscal_info.get('fiscal_year', 'N/A')}\n")
                    f.write(f"Quarter: {fiscal_info.get('quarter', 'N/A')}\n")
                    f.write(f"Date: {fiscal_info.get('date', 'N/A')}\n")
                    f.write(f"Transcript Date: {transcript_data.get('date', 'N/A')}\n")
                    f.write("\n" + "="*60 + "\n\n")
                
                content = transcript_data.get('content', '')
                speakers_content = self._extract_speaker_content(content)
                
                if speakers_content:
                    for item in speakers_content:
                        f.write(f"[{item['speaker']}]\n{item['content']}\n\n" + "-"*40 + "\n\n")
                else:
                    f.write("RAW TRANSCRIPT CONTENT:\n" + "-"*40 + "\n" + content)
            
            logger.info(f"Transcript saved to: {txt_filename}")
            return txt_filename
        except Exception as e:
            logger.error(f"保存transcript TXT文件时出错: {e}")
            return None

# 主业务逻辑
class SECEarningsAnalyzer:
    """SEC & 财报分析器主类"""
    
    def __init__(self):
        self.gemini_service = GeminiService()
        self.cache_manager = CacheManager()
        self.sec_service = SECService(self.cache_manager)
        self.hk_service = HKStockService(self.cache_manager)
        self.saudi_service = SaudiExchangeService(self.cache_manager)
        self.earnings_service = EarningsService(self.cache_manager)
        self.session_manager = SessionManager()
        self.document_manager = DocumentManager()

    def analyze_question(self, question: str, ticker: str, model_type: str) -> Tuple[str, str]:
        """分析用户问题并生成提示词"""
        # 获取当前语言设置
        language = st.session_state.get("selected_language", "English")
        
        if language == "English":
            analysis_prompt = f"""
            You are a professional financial analyst assistant, specialized in analyzing user questions and breaking them down into two key processing steps.

            User Question: {question}
            Stock Ticker: {ticker}

            Your Task:
            1. Analyze the user's question and understand its core intent
            2. Generate two high-quality prompts:
               - Document Processing Prompt: Used to extract information related to the user's question from a single document
               - Integration Prompt: Used to integrate analysis results from multiple document processing responses

            Requirements:
            - The document processing prompt must be specific and professional, capable of extracting all relevant information from a single document
            - The integration prompt must be able to integrate results from multiple documents, providing complete analysis and insights
            - Both prompts should be concise and clear, highlighting key points
            - The generated prompts should produce professional, readable analysis results
            - The user's original question MUST appear in both the document processing prompt and integration prompt
            - Always answer in English
            - **Must return only JSON format, do not include any other text or explanations.**

            Please return directly in JSON format:
            ```json
            {{
                "processing_prompt": "Document processing prompt",
                "integration_prompt": "Integration prompt"
            }}
            ```
            """
        elif language == "العربية":
            analysis_prompt = f"""
            أنت مساعد محلل مالي محترف، متخصص في تحليل أسئلة المستخدمين وتقسيمها إلى خطوتين رئيسيتين للمعالجة.

            سؤال المستخدم: {question}
            رمز السهم: {ticker}

            مهمتك:
            1. تحليل سؤال المستخدم وفهم قصده الأساسي
            2. توليد مطالبتين عالية الجودة:
               - مطالبة معالجة المستند: تستخدم لاستخراج المعلومات المتعلقة بسؤال المستخدم من مستند واحد
               - مطالبة التكامل: تستخدم لدمج نتائج التحليل من ردود معالجة المستندات المتعددة

            المتطلبات:
            - يجب أن تكون مطالبة معالجة المستند محددة ومهنية، قادرة على استخراج جميع المعلومات ذات الصلة من مستند واحد
            - يجب أن تكون مطالبة التكامل قادرة على دمج نتائج من مستندات متعددة، وتقديم تحليل ورؤى كاملة
            - يجب أن تكون كلا المطالبتين موجزة وواضحة، مع تسليط الضوء على النقاط الرئيسية
            - يجب أن تنتج المطالبات المولدة نتائج تحليل مهنية وقابلة للقراءة
            - يجب أن يظهر السؤال الأصلي للمستخدم في كل من مطالبة معالجة المستند ومطالبة التكامل
            - اجب دائماً باللغة العربية
            - **يجب إرجاع تنسيق JSON فقط، لا تشمل أي نص أو تفسيرات أخرى.**

            يرجى الإرجاع مباشرة بتنسيق JSON:
            ```json
            {{
                "processing_prompt": "مطالبة معالجة المستند",
                "integration_prompt": "مطالبة التكامل"
            }}
            ```
            """
        else:  # 中文
            analysis_prompt = f"""
            你是一个专业的金融分析师助手，专门负责分析用户的问题并将其分解为两个关键的处理步骤。

            用户问题: {question}
            股票代码: {ticker}

            你的任务：
            1. 分析用户的问题，理解其核心意图
            2. 生成两个高质量的提示词：
               - 处理资料prompt：用于从单个文档中提取 與用户问题 相关的信息
               - 统整prompt：用于整合多个 处理资料回答 的分析结果

            要求：
            - 处理资料prompt必须具体、专业，能够从单个文档中提取所有相关信息
            - 统整prompt必须能够整合多个文档的结果，提供完整的分析和洞察
            - 两个prompt都要简洁明了，重点突出
            - 生成的prompt应该能够产生专业、易读的分析结果
            - 用戶原始問題 必須在處理資料prompt 和 統整prompt 中都出現
            - **必须只返回JSON格式，不要包含任何其他文本或解释。**

            请直接返回JSON格式：
            ```json
            {{
                "processing_prompt": "处理资料prompt",
                "integration_prompt": "统整prompt"
            }}
            ```
            """
        
        try:
            result = self.gemini_service.call_api(analysis_prompt, model_type)
            # 尝试从Markdown代码块中提取JSON
            match = re.search(r"```json\s*(\{.*?\})\s*```", result, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = result # 如果没有markdown，则假定整个字符串是JSON
            
            prompt_data = json.loads(json_str)
            
            processing_prompt = prompt_data.get("processing_prompt", "")
            integration_prompt = prompt_data.get("integration_prompt", "")
            
            if not processing_prompt or not integration_prompt:
                raise ValueError("生成的提示词为空")
            
            return processing_prompt, integration_prompt
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析prompt JSON失败: {e}. 模型返回: {result}")
            # 使用默认提示词
            if language == "English":
                processing_prompt = f"Please extract information related to '{question}' from the following document and provide detailed analysis. Keep answers concise and to the point. Start with conclusions, use appropriate emojis and markdown format. If not found, briefly state 'Not mentioned in document'. Always answer in English."
                integration_prompt = f"Please integrate all the following analysis results to answer the user's question: '{question}', and provide a complete analysis report. Keep answers concise and to the point. Start with conclusions, use appropriate emojis and markdown format. If not found, briefly state 'Not mentioned in documents'. Always answer in English."
            elif language == "العربية":
                processing_prompt = f"يرجى استخراج المعلومات المتعلقة بـ '{question}' من المستند التالي وتقديم تحليل مفصل. اجعل الإجابات موجزة ومباشرة. ابدأ بالنتائج، استخدم الرموز التعبيرية المناسبة وتنسيق markdown. إذا لم توجد، اذكر بإيجاز 'غير مذكور في المستند'. اجب دائماً باللغة العربية."
                integration_prompt = f"يرجى دمج جميع نتائج التحليل التالية للإجابة على سؤال المستخدم: '{question}'، وتقديم تقرير تحليل كامل. اجعل الإجابات موجزة ومباشرة. ابدأ بالنتائج، استخدم الرموز التعبيرية المناسبة وتنسيق markdown. إذا لم توجد، اذكر بإيجاز 'غير مذكور في المستندات'. اجب دائماً باللغة العربية."
            else:  # 中文
                processing_prompt = f"请从以下文档中提取与'{question}'相关的信息，并进行详细分析，只回答重點就好，記得不廢話。回答要結論先說，可以適當使用emoji，markdown格式，如果沒找到就簡短回答，說未提及就好。"
                integration_prompt = f"请整合以下所有分析结果，回答用户问题：'{question}'，并提供完整的分析报告，只回答重點就好，記得不廢話。回答要結論先說，可以適當使用emoji，markdown格式，如果沒找到就簡短回答，說未提及就好。"
            
            return processing_prompt, integration_prompt
    
    def generate_fast_mode_prompt(self, question: str, ticker: str, model_type: str) -> str:
        """生成快速模式的分析提示词"""
        # 获取当前语言设置
        language = st.session_state.get("selected_language", "English")
        
        if language == "English":
            analysis_prompt = f"""
            You are a professional financial analyst assistant, specialized in analyzing user questions and generating optimized prompts for fast document analysis.

            User Question: {question}
            Stock Ticker: {ticker}

            Your Task:
            Generate a single, comprehensive prompt that can analyze all provided documents at once to answer the user's question.

            Requirements:
            - The prompt should be optimized for processing multiple documents simultaneously
            - It should extract and synthesize information from all documents to provide a complete answer
            - The prompt should be professional and capable of producing structured, readable analysis
            - The user's original question MUST appear in the generated prompt
            - Always answer in English
            - **Must return only JSON format, do not include any other text or explanations.**

            Please return directly in JSON format:
            ```json
            {{
                "fast_mode_prompt": "Comprehensive analysis prompt for all documents"
            }}
            ```
            """
        elif language == "العربية":
            analysis_prompt = f"""
            أنت مساعد محلل مالي محترف، متخصص في تحليل أسئلة المستخدمين وتوليد مطالبات محسنة للتحليل السريع للمستندات.

            سؤال المستخدم: {question}
            رمز السهم: {ticker}

            مهمتك:
            توليد مطالبة شاملة واحدة يمكنها تحليل جميع المستندات المقدمة دفعة واحدة للإجابة على سؤال المستخدم.

            المتطلبات:
            - يجب أن تكون المطالبة محسنة لمعالجة مستندات متعددة في نفس الوقت
            - يجب أن تستخرج وتدمج المعلومات من جميع المستندات لتقديم إجابة كاملة
            - يجب أن تكون المطالبة مهنية وقادرة على إنتاج تحليل منظم وقابل للقراءة
            - يجب أن يظهر السؤال الأصلي للمستخدم في المطالبة المولدة
            - اجب دائماً باللغة العربية
            - **يجب إرجاع تنسيق JSON فقط، لا تشمل أي نص أو تفسيرات أخرى.**

            يرجى الإرجاع مباشرة بتنسيق JSON:
            ```json
            {{
                "fast_mode_prompt": "مطالبة تحليل شاملة لجميع المستندات"
            }}
            ```
            """
        else:  # 中文
            analysis_prompt = f"""
            你是一个专业的金融分析师助手，专门负责分析用户问题并生成优化的快速文档分析提示词。

            用户问题: {question}
            股票代码: {ticker}

            你的任务：
            生成一个综合性的提示词，能够一次性分析所有提供的文档来回答用户的问题。

            要求：
            - 提示词应该针对同时处理多个文档进行优化
            - 应该能够从所有文档中提取和综合信息，提供完整的答案
            - 提示词应该专业，能够产生结构化、易读的分析结果
            - 用户原始问题必须出现在生成的提示词中
            - **必须只返回JSON格式，不要包含任何其他文本或解释。**

            请直接返回JSON格式：
            ```json
            {{
                "fast_mode_prompt": "综合分析所有文档的提示词"
            }}
            ```
            """
        
        try:
            result = self.gemini_service.call_api(analysis_prompt, model_type)
            # 尝试从Markdown代码块中提取JSON
            match = re.search(r"```json\s*(\{.*?\})\s*```", result, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = result
            
            prompt_data = json.loads(json_str)
            
            fast_mode_prompt = prompt_data.get("fast_mode_prompt", "")
            
            if not fast_mode_prompt:
                raise ValueError("生成的快速模式提示词为空")
            
            return fast_mode_prompt
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析快速模式prompt JSON失败: {e}. 模型返回: {result}")
            # 使用默认提示词
            if language == "English":
                return f"Please analyze all the provided documents to answer the user's question: '{question}'. Extract relevant information from all documents and provide a comprehensive analysis. Keep answers concise and to the point. Start with conclusions, use appropriate emojis and markdown format. If not found, briefly state 'Not mentioned in documents'. Always answer in English."
            elif language == "العربية":
                return f"يرجى تحليل جميع المستندات المقدمة للإجابة على سؤال المستخدم: '{question}'. استخرج المعلومات ذات الصلة من جميع المستندات وقدم تحليلاً شاملاً. اجعل الإجابات موجزة ومباشرة. ابدأ بالنتائج، استخدم الرموز التعبيرية المناسبة وتنسيق markdown. إذا لم توجد، اذكر بإيجاز 'غير مذكور في المستندات'. اجب دائماً باللغة العربية."
            else:  # 中文
                return f"请分析所有提供的文档来回答用户问题：'{question}'。从所有文档中提取相关信息并提供综合分析。只回答重点就好，记得不废话。回答要结论先说，可以适当使用emoji，markdown格式，如果没找到就简短回答，说未提及就好。"
    
    def process_document(self, document: Document, processing_prompt: str, model_type: str) -> str:
        """处理单个文档"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            # 如果文档内容为空，则下载
            if not document.content:
                if document.type == 'SEC Filing':
                    # 检查是否为6-K文件
                    if hasattr(document, 'form_type') and document.form_type == '6-K':
                        # 6-K文件应该已经在SixKProcessor中处理过了。如果这里内容仍然为空，说明没有找到ex99附件
                        logger.info(f"ℹ️ [6K-PROCESS] 6-K文件内容为空: {document.title} (可能没有ex99附件)")
                        if language == "中文":
                            document.content = "6-K文件未包含ex99附件"
                        elif language == "العربية":
                            document.content = "ملف 6-K لا يحتوي على مرفقات ex99"
                        else:
                            document.content = "6-K file contains no ex99 attachments"
                    else:
                        # 普通SEC文件处理
                        document.content = self.sec_service.download_filing(document.url)
                elif document.type == 'HK Stock Filing':
                    # 港股文件处理
                    document.content = self.hk_service.download_hk_filing(document.url)
                elif document.type == 'Saudi Exchange Filing':
                    # 沙特交易所文件处理
                    document.content = self.saudi_service.download_saudi_filing(document.url)
                elif document.type == 'Earnings Call':
                    # 在新的流程中，内容已预先获取
                    logger.warning(f"处理文档时发现财报记录内容为空: {document.title}")
                    document.content = "内容未找到" if language == "中文" else "Content not found"
            
            # 准备prompt - 根据语言选择
            if language == "English":
                prompt = f"""
                You are a professional document analyst, specialized in extracting and analyzing information from financial documents.

                Document Title: {document.title}
                Document Date: {document.date}
                Document Type: {document.type}
                
                Processing Requirements: {processing_prompt}
                Also answer similar requirements, don't miss anything
                
                Requirements:
                - Carefully read the provided document content
                - Extract relevant information according to the user's specific requirements
                - Provide accurate, professional analysis
                - Ensure answers come from document content, don't imagine
                - I don't have time to read, ensure answers are direct and to the point, no need for polite conversation
                - Always answer in English
                - when markdown output, Escape all dollar signs $ for currency as ＄ to prevent Markdown from rendering them as math.
                
                Answer Requirements:
                - Start with 📍 emoji, followed by what type of document this is and its purpose, 
                - second line Start with 💡 on next new line row, directly state conclusions, answer conclusions related to my processing requirements, all in short sentences
                - Please provide structured analysis results, only answer key points, remember no nonsense.
                - First sentence should state key points without pleasantries. Don't say "According to the document content you provided..." such nonsense, directly state key points
                - Answer should start with conclusions, can use emojis to help users read, markdown format
                - If the document doesn't contain information related to my question, just say "Not mentioned in document" period, one sentence only, no nonsense, I don't have time to read

                Document Content:
                {document.content}
                """
            else:  # 中文
                prompt = f"""
                你是一个专业的文档分析师，专门负责从财务文档中提取和分析信息。

                文档标题: {document.title}
                文档日期: {document.date}
                文档类型: {document.type}
                
                处理要求: {processing_prompt}
                有與以上要求類似的也一起回答，不要漏掉
                
                要求：
                - 仔细阅读提供的文档内容
                - 根据用户的具体要求提取相关信息
                - 提供准确、专业的分析
                - 確保回答都來自文檔內容，不要憑空想像
                - 我沒時間看 確保回答直接說重點 不用像人一樣還要客套話
                - markdown輸出，將所有表示金額的 $ 改為 ＄，以避免 Markdown 被誤判為數學公式。
                
                回答要求：
                - 開頭以📍这个emoji开頭， 📍後面接這是一份什麼文件，文件目的是什麼，
                - 第二句下一行，開頭以 💡，記得換行，直接說結論，回答跟我处理要求有關的結論 都是簡短一句話
                - 请提供结构化的分析结果，只回答重點就好，記得不廢話。
                - 第一句就說重點不用客套。 不用說 根据您提供的文档内容... 這種廢話，直接說重點
                - 回答要結論先說，可以使用emoji幫助使用者閱讀，markdown格式
                - 如果文檔內沒有跟我的問題有關的資訊，就說一句 文檔內未提及 句號 一句話就好  不准廢話 我沒時間看

                文档内容:
                {document.content}
                """
            
            logger.info("================================================")
            logger.info(f"Processing document: {document.title} in {language}")
            
            return self.gemini_service.call_api(prompt, model_type)
            
        except Exception as e:
            logger.error(f"处理文档失败: {e}")
            error_msg = f"处理文档时出错: {e}" if language == "中文" else f"Error processing document: {e}"
            return error_msg
    
    def process_document_stream(self, document: Document, processing_prompt: str, model_type: str):
        """处理单个文档 - 流式响应版本"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            # 如果文档内容为空，则下载
            if not document.content:
                if document.type == 'SEC Filing':
                    # 检查是否为6-K文件
                    if hasattr(document, 'form_type') and document.form_type == '6-K':
                        # 6-K文件应该已经在SixKProcessor中处理过了。如果这里内容仍然为空，说明没有找到ex99附件
                        logger.info(f"ℹ️ [6K-PROCESS] 6-K文件内容为空: {document.title} (可能没有ex99附件)")
                        if language == "中文":
                            document.content = "6-K文件未包含ex99附件"
                        elif language == "العربية":
                            document.content = "ملف 6-K لا يحتوي على مرفقات ex99"
                        else:
                            document.content = "6-K file contains no ex99 attachments"
                    else:
                        # 普通SEC文件处理
                        document.content = self.sec_service.download_filing(document.url)
                elif document.type == 'HK Stock Filing':
                    # 港股文件处理
                    document.content = self.hk_service.download_hk_filing(document.url)
                elif document.type == 'Saudi Exchange Filing':
                    # 沙特交易所文件处理
                    document.content = self.saudi_service.download_saudi_filing(document.url)
                elif document.type == 'Earnings Call':
                    # 在新的流程中，内容已预先获取
                    logger.warning(f"处理文档时发现财报记录内容为空: {document.title}")
                    document.content = "内容未找到" if language == "中文" else "Content not found"
            
            # 准备prompt - 根据语言选择
            if language == "English":
                prompt = f"""
                You are a professional document analyst, specialized in extracting and analyzing information from financial documents.

                Document Title: {document.title}
                Document Date: {document.date}
                Document Type: {document.type}
                
                Processing Requirements: {processing_prompt}
                Also answer similar requirements, don't miss anything
                
                Requirements:
                - Carefully read the provided document content
                - Extract relevant information according to the user's specific requirements
                - Provide accurate, professional analysis
                - Ensure answers come from document content, don't imagine
                - I don't have time to read, ensure answers are direct and to the point, no need for polite conversation
                - Always answer in English
                - when markdown output, Escape all dollar signs $ for currency as ＄ to prevent Markdown from rendering them as math.
                
                Answer Requirements:
                - Start with 📍 emoji, followed by what type of document this is and its purpose, 
                - second line Start with 💡 on next new line row, directly state conclusions, answer conclusions related to my processing requirements, all in short sentences
                - Please provide structured analysis results, only answer key points, remember no nonsense.
                - First sentence should state key points without pleasantries. Don't say "According to the document content you provided..." such nonsense, directly state key points
                - Answer should start with conclusions, can use emojis to help users read, markdown format
                - If the document doesn't contain information related to my question, just say "Not mentioned in document" period, one sentence only, no nonsense, I don't have time to read

                Document Content:
                {document.content}
                """
            else:  # 中文
                prompt = f"""
                你是一个专业的文档分析师，专门负责从财务文档中提取和分析信息。

                文档标题: {document.title}
                文档日期: {document.date}
                文档类型: {document.type}
                
                处理要求: {processing_prompt}
                有與以上要求類似的也一起回答，不要漏掉
                
                要求：
                - 仔细阅读提供的文档内容
                - 根据用户的具体要求提取相关信息
                - 提供准确、专业的分析
                - 確保回答都來自文檔內容，不要憑空想像
                - 我沒時間看 確保回答直接說重點 不用像人一樣還要客套話
                - markdown輸出，將所有表示金額的 $ 改為 ＄，以避免 Markdown 被誤判為數學公式。


                
                回答要求：
                - 開頭以📍这个emoji开頭， 📍後面接這是一份什麼文件，文件目的是什麼，
                - 第二句下一行，開頭以 💡，記得換行，直接說結論，回答跟我处理要求有關的結論 都是簡短一句話
                - 请提供结构化的分析结果，只回答重點就好，記得不廢話。
                - 第一句就說重點不用客套。 不用說 根据您提供的文档内容... 這種廢話，直接說重點
                - 回答要結論先說，可以使用emoji幫助使用者閱讀，markdown格式
                - 如果文檔內沒有跟我的問題有關的資訊，就說一句 文檔內未提及 句號 一句話就好  不准廢話 我沒時間看

                文档内容:
                {document.content}
                """
            
            logger.info("================================================")
            logger.info(f"Processing document (streaming): {document.title} in {language}")
            
            # 返回流式响应生成器
            return self.gemini_service.call_api_stream(prompt, model_type)
            
        except Exception as e:
            logger.error(f"处理文档失败: {e}")
            error_msg = f"处理文档时出错: {e}" if language == "中文" else f"Error processing document: {e}"
            # 对于错误，返回一个简单的生成器
            def error_generator():
                yield error_msg
            return error_generator()

    def integrate_results(self, document_results: List[Dict], integration_prompt: str, user_question: str, ticker: str, model_type: str) -> str:
        """整合分析结果"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            # 构建整合提示词
            if language == "English":
                integration_input = f"""
                You are a professional financial analyst, specialized in integrating analysis results from multiple documents.

                User Question: {user_question}
                Stock Ticker: {ticker}
                
                Integration Requirements: {integration_prompt}
                
                Requirements:
                - If the content contains numbers for the same indicator at different time points, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator numbers. Then explain below the pivot table after generation.
                - If the content contains business descriptions for the same indicator at different time points, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator descriptions. Then explain below the pivot table after generation.
                - For example: row1 would be Indicator, 2025Q1, 2025Q2. row2 would be AI commercialization, Q2 expected to resume double-digit year-over-year growth, confident in achieving significant revenue growth for full year 2025
                - table output use markdown format, ensure markdown format is correct, no errors
                - Comprehensively analyze all provided document analysis results
                - Identify trends, patterns, and key changes
                - Provide deep insights and professional recommendations
                - Use tables, lists, and other formats to enhance readability
                - Highlight key information and critical findings
                - This is a comprehensive summary, don't repeat detailed content from individual documents
                - Focus on cross-document trends and correlations
                - Always answer in English
                
                Document Analysis Results:
                """
            else:  # 中文
                integration_input = f"""
                你是一个专业的金融分析师，专门负责整合多个文档的分析结果。

                用户问题: {user_question}
                股票代码: {ticker}
                
                整合要求: {integration_prompt}
                
                要求：
                - 如果內文有 同指標不同時間點的 數字，回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。然後pivot table 生成完 表格下方解釋一下
                - 如果內文有 同指標不同時間點的 業務的描述，回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。然後pivot table 生成完 表格下方解釋一下
                - - 舉例類似像是  row1會是 指標, 2025Q1, 2025Q2 。 row2會是 AI商业化, Q2预计将恢复两位数同比增长, 有信心在2025全年年实现显著收入增长
                - table 都用markdown格式，要確保markdown格式正確，不要有錯誤
                - 综合分析所有提供的文档分析结果
                - 识别趋势、模式和关键变化
                - 提供深入的洞察和专业建议
                - 使用表格、列表等格式增强可读性
                - 突出重点信息和关键发现
                - 这是一个综合总结，不要重复单个文档的详细内容
                - 重点关注跨文档的趋势和关联性
                
                文档分析结果:
                """
            
            for result in document_results:
                integration_input += f"""
                
                === {result['title']} ({result['date']}) ===
                {result['analysis']}
                """
            
            completion_text = "Please provide a complete, professional comprehensive analysis report and summary." if language == "English" else "请提供完整、专业的综合分析报告和总结。"
            integration_input += f"\n\n{completion_text}"
            
            return self.gemini_service.call_api(integration_input, model_type)
            
        except Exception as e:
            logger.error(f"整合结果失败: {e}")
            error_msg = f"整合结果时出错: {e}" if st.session_state.get("selected_language", "English") == "中文" else f"Error integrating results: {e}"
            return error_msg
    
    def integrate_results_stream(self, document_results: List[Dict], integration_prompt: str, user_question: str, ticker: str, model_type: str):
        """整合分析结果 - 流式响应版本"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            # 构建整合提示词
            if language == "English":
                integration_input = f"""
                You are a professional financial analyst, specialized in integrating analysis results from multiple documents.

                User Question: {user_question}
                Stock Ticker: {ticker}
                
                Integration Requirements: {integration_prompt}
                
                Requirements:
                - If the content contains numbers for the same indicator at different time points, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator numbers. Then explain below the pivot table after generation.
                - If the content contains business descriptions for the same indicator at different time points, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator descriptions. Then explain below the pivot table after generation.
                - For example: row1 would be Indicator, 2025Q1, 2025Q2. row2 would be AI commercialization, Q2 expected to resume double-digit year-over-year growth, confident in achieving significant revenue growth for full year 2025
                - table output use markdown format, ensure markdown format is correct, no errors
                - Comprehensively analyze all provided document analysis results
                - Identify trends, patterns, and key changes
                - Provide deep insights and professional recommendations
                - Use tables, lists, and other formats to enhance readability
                - Highlight key information and critical findings
                - This is a comprehensive summary, don't repeat detailed content from individual documents
                - Focus on cross-document trends and correlations
                - Always answer in English
                
                Document Analysis Results:
                """
            else:  # 中文
                integration_input = f"""
                你是一个专业的金融分析师，专门负责整合多个文档的分析结果。

                用户问题: {user_question}
                股票代码: {ticker}
                
                整合要求: {integration_prompt}
                
                要求：
                - 如果內文有 同指標不同時間點的 數字，回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。然後pivot table 生成完 表格下方解釋一下
                - 如果內文有 同指標不同時間點的 業務的描述，回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。然後pivot table 生成完 表格下方解釋一下
                - - 舉例類似像是  row1會是 指標, 2025Q1, 2025Q2 。 row2會是 AI商业化, Q2预计将恢复两位数同比增长, 有信心在2025全年年实现显著收入增长
                - table 都用markdown格式，要確保markdown格式正確，不要有錯誤
                - 综合分析所有提供的文档分析结果
                - 识别趋势、模式和关键变化
                - 提供深入的洞察和专业建议
                - 使用表格、列表等格式增强可读性
                - 突出重点信息和关键发现
                - 这是一个综合总结，不要重复单个文档的详细内容
                - 重点关注跨文档的趋势和关联性
                
                文档分析结果:
                """
            
            for result in document_results:
                integration_input += f"""
                
                === {result['title']} ({result['date']}) ===
                {result['analysis']}
                """
            
            completion_text = "Please provide a complete, professional comprehensive analysis report and summary." if language == "English" else "请提供完整、专业的综合分析报告和总结。"
            integration_input += f"\n\n{completion_text}"
            
            # 返回流式响应生成器
            return self.gemini_service.call_api_stream(integration_input, model_type)
            
        except Exception as e:
            logger.error(f"整合结果失败: {e}")
            error_msg = f"整合结果时出错: {e}" if st.session_state.get("selected_language", "English") == "中文" else f"Error integrating results: {e}"
            # 对于错误，返回一个简单的生成器
            def error_generator():
                yield error_msg
            return error_generator()
    
    def process_all_documents_fast(self, documents: List[Document], fast_mode_prompt: str, model_type: str):
        """快速模式：一次性处理所有文档 - 流式响应版本"""
        try:
            # 获取当前语言设置
            language = st.session_state.get("selected_language", "English")
            
            # 预处理6-K文件
            logger.info(f"🔍 [6K-FAST] 开始预处理文档，总数: {len(documents)}")
            
            # 调试日志：显示传入的文档
            for i, doc in enumerate(documents):
                logger.info(f"🔍 [6K-FAST] 传入文档{i+1}: {doc.title}, 类型: {doc.type}, form_type: {getattr(doc, 'form_type', 'None')}")
            
            processed_documents = []
            
            for i, document in enumerate(documents):
                logger.info(f"🔍 [6K-FAST] 处理文档{i+1}: {document.title}, 类型: {document.type}")
                logger.info(f"🔍 [6K-FAST] 文档属性: form_type={getattr(document, 'form_type', 'None')}, date={document.date}")
                
                # 特殊处理6-K文件
                if hasattr(document, 'form_type') and document.form_type == '6-K':
                    logger.info(f"🔍 [6K-FAST] ✅ 进入6-K处理分支: {document.title}")
                    logger.info(f"🔍 [6K-FAST] 检测到6-K文件，开始处理: {document.title}")
                    
                    # 初始化6-K处理器
                    self.sec_service._init_sixk_processor(self.document_manager.temp_dir)
                    
                    # 获取ticker和CIK
                    ticker = st.session_state.analyzer_ticker
                    ticker_map = self.sec_service.get_cik_map()
                    cik = ticker_map.get(ticker.upper(), '')
                    
                    logger.info(f"🔍 [6K-FAST] 6-K处理参数: Ticker={ticker}, CIK={cik}")
                    
                    # 处理6-K文件
                    processed_6k_docs = self.sec_service.sixk_processor.process_6k_filing(
                        ticker, cik, document.url, document
                    )
                    
                    logger.info(f"🔍 [6K-FAST] 6-K处理结果: {len(processed_6k_docs)} 个文档")
                    
                    if processed_6k_docs:
                        processed_documents.extend(processed_6k_docs)
                        logger.info(f"✅ [6K-FAST] 6-K文件处理成功，添加 {len(processed_6k_docs)} 个文档")
                    else:
                        logger.info(f"ℹ️ [6K-FAST] 6-K文件没有ex99附件，跳过")
                        # 不添加空的6-K文档
                else:
                    # 非6-K文件，直接添加
                    logger.info(f"🔍 [6K-FAST] ✅ 非6-K文件，直接添加: {document.title}")
                    processed_documents.append(document)
            
            logger.info(f"🔍 [6K-FAST] 预处理完成，最终文档数: {len(processed_documents)}")
            
            # 下载所有文档内容
            all_content = ""
            for i, document in enumerate(processed_documents):
                if not document.content:
                    if document.type == 'SEC Filing':
                        document.content = self.sec_service.download_filing(document.url)
                    elif document.type == 'HK Stock Filing':
                        document.content = self.hk_service.download_hk_filing(document.url)
                    elif document.type == 'Saudi Exchange Filing':
                        document.content = self.saudi_service.download_saudi_filing(document.url)
                    elif document.type == 'Earnings Call':
                        logger.warning(f"处理文档时发现财报记录内容为空: {document.title}")
                        document.content = "内容未找到" if language == "中文" else "Content not found"
                
                # 添加文档分隔符和标题
                separator = f"\n\n{'='*60}\n"
                doc_header = f"文档 {i+1}: {document.title}\n日期: {document.date}\n类型: {document.type}\n" if language == "中文" else f"Document {i+1}: {document.title}\nDate: {document.date}\nType: {document.type}\n"
                separator += doc_header
                separator += f"{'='*60}\n\n"
                
                all_content += separator + (document.content or "")
            
            # 限制总内容长度
            if len(all_content) > config.MAX_CONTENT_LENGTH:
                all_content = all_content[:config.MAX_CONTENT_LENGTH] + f"\n[内容已截断]" if language == "中文" else f"\n[Content truncated]"
            
            # 构建完整的提示词
            if language == "English":
                prompt = f"""
                You are a professional financial analyst, specialized in analyzing multiple financial documents simultaneously.

                Analysis Requirements: {fast_mode_prompt}
                
                Requirements:
                - Analyze all provided documents comprehensively
                - Extract relevant information according to the user's specific requirements
                - Provide accurate, professional analysis
                - Ensure answers come from document content, don't imagine
                - I don't have time to read, ensure answers are direct and to the point, no need for polite conversation
                - Always answer in English
                - when markdown output, Escape all dollar signs $ for currency as ＄ to prevent Markdown from rendering them as math.
                
                Answer Requirements:
                - Start with 📊 emoji, followed by a brief summary of what documents were analyzed
                - Second line Start with 💡 on next new line row, directly state conclusions related to the user's question
                - Please provide structured analysis results, only answer key points, remember no nonsense
                - First sentence should state key points without pleasantries
                - Answer should start with conclusions, can use emojis to help users read, markdown format
                - If the documents don't contain information related to the question, just say "Not mentioned in documents" period, one sentence only
                
                Table Requirements:
                - If the content contains numbers for the same indicator at different time points, or question is about guidance, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator numbers. put both guidance and actual numbers from next quarter report.Then explain below the pivot table after generation.
                - If the content contains business descriptions for the same indicator at different time points, or question is about guidance, place a pivot table at the very beginning of the answer. Format: pivot table row names are different indicators, column names are the time when indicators were published, cells are the indicator descriptions. put both guidance and actual numbers from next quarter report.Then explain below the pivot table after generation.
                - table output use markdown format, ensure markdown format is correct, no errors
                - 如果問guidance，table 格式如下，注意 如果問整理guidance 都是要整理出文件內所有的季度的
                - - column name 是不同文件的時間，所有有提到的文件都要納入，同一天的統整在一起。
                - - row name 就是指表 像是 收入 毛利率 或是 DAU MAU 這種指標，分成actual 和 guidance。actual 就是放財報內實際公布的數字，guidance就是放earning call或是證交所公告內給的對未來的guidance數字或是描述
                example:
                |              | 2025Q1 (2025/1/20) | 2025Q2 (2025/4/20) | 2025Q3 (2025/7/20) | 8-K (2025/8/20) |
                |--------------|--------------------|--------------------|--------------------|-----------------|
                | DAU Actual   | 3亿                | 3.5亿              | 4亿                |                 |
                | DAU Guidance | 预计Q2達到3.5億    | 预计Q3達到4億      | 预计Q4達到4.5億    | 预计Q4達到6億   |
                | GMV Actual   | 100亿              | 200亿              | 300亿              |                 |
                | GMV Guidance | 预计Q2達到200億    | 预计Q3達到250億    | 预计Q4達到300億    | 预计Q4達到500億 |
                - 如果有其他整理成表格的任務，第一個table 格式也要跟上變一樣的 column name 是不同時間，row name 是不同指標。然後第二個table 才是詳細的表格
                - 變化這個字眼，如果問的是變化，就是把多個時間點的資料，整理成表格，下面再文字說明，注意是多個時間點的資料，不是只有兩個時間點的資料

                All Document Contents:
                {all_content}
                """
            elif language == "العربية":
                prompt = f"""
                أنت محلل مالي محترف، متخصص في تحليل مستندات مالية متعددة في نفس الوقت.

                متطلبات التحليل: {fast_mode_prompt}
                
                المتطلبات:
                - تحليل جميع المستندات المقدمة بشكل شامل
                - استخراج المعلومات ذات الصلة وفقاً لمتطلبات المستخدم المحددة
                - تقديم تحليل دقيق ومهني
                - تأكد من أن الإجابات تأتي من محتوى المستندات، لا تتخيل
                - ليس لدي وقت للقراءة، تأكد من أن الإجابات مباشرة ومحددة، لا حاجة للمحادثة المهذبة
                - اجب دائماً باللغة العربية
                - عند إخراج markdown، تجنب استخدام $ للعملة واستخدم ＄ لمنع Markdown من عرضها كرياضيات.
                
                متطلبات الإجابة:
                - ابدأ بـ 📊 emoji، متبوعاً بملخص موجز للمستندات التي تم تحليلها
                - السطر الثاني يبدأ بـ 💡 في سطر جديد، اذكر النتائج مباشرة المتعلقة بسؤال المستخدم
                - يرجى تقديم نتائج تحليل منظمة، أجب على النقاط الرئيسية فقط، تذكر عدم الثرثرة
                - الجملة الأولى يجب أن تذكر النقاط الرئيسية بدون مجاملات
                - يجب أن تبدأ الإجابة بالنتائج، يمكن استخدام الرموز التعبيرية لمساعدة المستخدمين على القراءة، تنسيق markdown
                - إذا لم تحتو المستندات على معلومات متعلقة بالسؤال، فقط قل "غير مذكور في المستندات" نقطة، جملة واحدة فقط
                
                متطلبات الجدول:
                - إذا احتوى المحتوى على أرقام لنفس المؤشر في نقاط زمنية مختلفة، أو كان السؤال حول التوجيهات، ضع جدولاً محورياً في بداية الإجابة. التنسيق: أسماء صفوف الجدول المحوري هي مؤشرات مختلفة، أسماء الأعمدة هي الوقت الذي تم نشر المؤشرات فيه، الخلايا هي أرقام المؤشرات. ضع كلاً من أرقام التوجيه والأرقام الفعلية من تقرير الربع التالي. ثم اشرح أسفل الجدول المحوري بعد الإنشاء.
                - إذا احتوى المحتوى على أوصاف تجارية لنفس المؤشر في نقاط زمنية مختلفة، أو كان السؤال حول التوجيهات، ضع جدولاً محورياً في بداية الإجابة. التنسيق: أسماء صفوف الجدول المحوري هي مؤشرات مختلفة، أسماء الأعمدة هي الوقت الذي تم نشر المؤشرات فيه، الخلايا هي أوصاف المؤشرات. ضع كلاً من أرقام التوجيه والأرقام الفعلية من تقرير الربع التالي. ثم اشرح أسفل الجدول المحوري بعد الإنشاء.
                - إخراج الجدول باستخدام تنسيق markdown، تأكد من أن تنسيق markdown صحيح، بدون أخطاء
                
                جميع محتويات المستندات:
                {all_content}
                """
            else:  # 中文
                prompt = f"""
                你是一个专业的金融分析师，专门负责同时分析多个金融文档。

                分析要求: {fast_mode_prompt}
                
                要求：
                - 全面分析所有提供的文档
                - 根据用户的具体要求提取相关信息
                - 提供准确、专业的分析
                - 确保回答都来自文档内容，不要凭空想象
                - 我没时间看，确保回答直接说重点，不用像人一样还要客套话
                - markdown输出，将所有表示金额的 $ 改为 ＄，以避免 Markdown 被误判为数学公式
                
                回答要求：
                - 开头以📊这个emoji开头，📊后面接简要说明分析了哪些文档
                - 第二句下一行，开头以💡，记得换行，直接说结论，回答跟用户问题有关的结论，都是简短一句话
                - 请提供结构化的分析结果，只回答重点就好，记得不废话
                - 第一句就说重点不用客套，直接说重点
                - 回答要结论先说，可以使用emoji帮助使用者阅读，markdown格式
                - 如果文档内没有跟问题有关的信息，就说一句"文档内未提及"句号，一句话就好，不准废话
                
                表格要求：
                - 如果內文有 同指標不同時間點的 數字 或是問guidance，問題適合整理成表格的 回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。guidance數字 還有下一季報出的 actual 數字 都要放。然後pivot table 生成完 表格下方解釋一下
                - 如果內文有 同指標不同時間點的 業務的描述 或是問guidance，問題適合整理成表格的 回答的最一開始 一定要放上一個pivot table，格式是 pivot table row name 是不同指標 ， column 指標公布的時間，cell 是指標的數字。guidance數字 還有下一季報出的 actual 數字 都要放。然後pivot table 生成完 表格下方解釋一下
                - table 都用markdown格式，要確保markdown格式正確，不要有錯誤
                - 如果問guidance，table 格式如下，注意 如果問整理guidance 都是要整理出文件內所有的季度的
                - - column name 是不同文件的時間，所有有提到的文件都要納入，同一天的統整在一起。
                - - row name 就是指表 像是 收入 毛利率 或是 DAU MAU 這種指標，分成actual 和 guidance。actual 就是放財報內實際公布的數字，guidance就是放earning call或是證交所公告內給的對未來的guidance數字或是描述
                example:
                |              | 2025Q1 (2025/1/20) | 2025Q2 (2025/4/20) | 2025Q3 (2025/7/20) | 8-K (2025/8/20) |
                |--------------|--------------------|--------------------|--------------------|-----------------|
                | DAU Actual   | 3亿                | 3.5亿              | 4亿                |                 |
                | DAU Guidance | 预计Q2達到3.5億    | 预计Q3達到4億      | 预计Q4達到4.5億    | 预计Q4達到6億   |
                | GMV Actual   | 100亿              | 200亿              | 300亿              |                 |
                | GMV Guidance | 预计Q2達到200億    | 预计Q3達到250億    | 预计Q4達到300億    | 预计Q4達到500億 |
                - 如果有其他整理成表格的任務，第一個table 格式也要跟上變一樣的 column name 是不同時間，row name 是不同指標。然後第二個table 才是詳細的表格
                - 變化這個字眼，如果問的是變化，就是把多個時間點的資料，整理成表格，下面再文字說明，注意是多個時間點的資料，不是只有兩個時間點的資料
                
                所有文档内容:
                {all_content}
                """
            
            logger.info("================================================")
            logger.info(f"Processing all documents in fast mode in {language}")
            
            # 返回流式响应生成器
            return self.gemini_service.call_api_stream(prompt, model_type)
            
        except Exception as e:
            logger.error(f"快速模式处理失败: {e}")
            error_msg = f"快速模式处理时出错: {e}" if language == "中文" else f"Error in fast mode processing: {e}"
            # 对于错误，返回一个简单的生成器
            def error_generator():
                yield error_msg
            return error_generator()

# 初始化应用
@st.cache_resource
def initialize_app():
    """初始化应用"""
    analyzer = SECEarningsAnalyzer()
    # 确保所有服务都已正确初始化
    logger.info(f"🔧 [INIT] 初始化完成，服务列表: {[attr for attr in dir(analyzer) if attr.endswith('_service')]}")
    return analyzer

# 主页面
def main():
    """主页面函数"""
    # 在应用初始化之前，确保session state已经存在
    try:
        SessionManager.init_session_state()
    except Exception as e:
        # 静默处理初始化错误
        logger.warning(f"Session state initialization warning: {e}")
        # 确保基本的session state存在
        if "analyzer_messages" not in st.session_state:
            st.session_state.analyzer_messages = []
        if "analyzer_ticker" not in st.session_state:
            st.session_state.analyzer_ticker = ""
    
    # 定义回退函数用于获取密钥
    def get_secret_value(key: str, default=None):
        """从 st.secrets 或环境变量中获取密钥值"""
        import os
        import json
        from pathlib import Path
        
        # 检查 secrets.toml 文件是否存在
        secrets_paths = [
            Path(".streamlit/secrets.toml"),
            Path("/root/.streamlit/secrets.toml"),
            Path("/app/.streamlit/secrets.toml")
        ]
        
        secrets_file_exists = any(path.exists() for path in secrets_paths)
        
        if secrets_file_exists:
            try:
                return st.secrets[key]
            except KeyError:
                # 如果 secrets.toml 存在但没有该键，回退到环境变量
                pass
        
        # 直接从环境变量读取
        env_value = os.environ.get(key, default)
        if env_value is None:
            return default
            
        # 尝试解析 JSON 格式的环境变量（用于列表类型的密钥）
        if isinstance(env_value, str) and env_value.startswith('[') and env_value.endswith(']'):
            try:
                return json.loads(env_value)
            except json.JSONDecodeError:
                return env_value
        
        return env_value
    
    # 處理URL參數
    query_params = st.query_params
    if "p" in query_params:
        param_value = query_params["p"]
        access_code = get_secret_value("ACCESS_CODE", "")
        if param_value.lower() == access_code.lower():
            st.session_state.use_premium_api = True
            st.session_state.premium_access_code = param_value
            st.success("🎉 已啟用付費API服務！")

    # 初始化应用
    analyzer = initialize_app()
    
    # 检查analyzer是否有所需的服务
    if not hasattr(analyzer, 'saudi_service'):
        st.error("❌ 应用初始化错误：缺少沙特交易所服务")
        st.info("🔄 正在清除缓存并重新初始化...")
        st.cache_resource.clear()
        st.rerun()
    
    # 获取当前语言设置
    current_language = st.session_state.get("selected_language", "English")
    lang_config = LANGUAGE_CONFIG[current_language]
    
    # 页面标题
    st.title(lang_config["title"])

    # 左侧边栏
    with st.sidebar:
        st.header(lang_config["sidebar_header"])
        
        # Ticker输入
        ticker_input = st.text_input(
            lang_config["ticker_label"],
            value=st.session_state.analyzer_ticker,
            placeholder=lang_config["ticker_placeholder"]
        )
        
        # 智能处理ticker格式
        if ticker_input:
            if is_saudi_stock(ticker_input):
                ticker = normalize_saudi_ticker(ticker_input)
                st.info(f"{lang_config['saudi_stock_info']} - {ticker}")
            elif is_hk_stock(ticker_input):
                ticker = normalize_hk_ticker(ticker_input)
                st.info(lang_config["hk_stock_info"].format(ticker))
            else:
                ticker = ticker_input.upper()
                st.info(lang_config["us_stock_info"])
        else:
            ticker = ""
        
        # 年份选择
        years = st.number_input(
            lang_config["years_label"],
            min_value=1,
            max_value=10,
            value=st.session_state.analyzer_years,
            step=1
        )
        
        # 动态显示 cutoff date
        current_year = datetime.now().year
        cutoff_date = datetime(current_year - years + 1, 1, 1).date()
        
        # 添加说明
        if current_language == "中文":
            st.caption(f"📅 Data Date: {cutoff_date} ~ now")
        else:
            st.caption(f"📅 Data Date: {cutoff_date} ~ now")
        
        # 数据类型选择 - 根据股票类型显示不同选项
        st.subheader(lang_config["data_type_header"])
        
        if is_saudi_stock(ticker):
            # 沙特交易所选项 - 简化为所有公告类型
            use_sec_reports = True  # 自动选择所有公告
            use_sec_others = True   # 自动选择所有公告
            use_earnings = False    # 沙特交易所没有earnings call
            
            # 显示信息给用户
            if current_language == "العربية":
                st.info("🇸🇦 سيتم تحليل جميع أنواع الإعلانات من السوق السعودية")
            elif current_language == "中文":
                st.info("🇸🇦 将分析沙特交易所的所有公告类型")
            else:
                st.info("🇸🇦 Will analyze all announcement types from Saudi Exchange")
                
        elif is_hk_stock(ticker):
            # 港股选项
            use_sec_reports = st.checkbox(lang_config["sec_reports_hk"], value=st.session_state.analyzer_use_sec_reports)
            use_sec_others = st.checkbox(lang_config["sec_others_hk"], value=st.session_state.analyzer_use_sec_others)
            
            use_earnings = st.checkbox(lang_config["earnings_label"], value=st.session_state.analyzer_use_earnings)
            st.caption(lang_config["earnings_caption"])
        else:
            # 美股选项
            use_sec_reports = st.checkbox(lang_config["sec_reports_us"], value=st.session_state.analyzer_use_sec_reports)
            use_sec_others = st.checkbox(lang_config["sec_others_us"], value=st.session_state.analyzer_use_sec_others)
            
            use_earnings = st.checkbox(lang_config["earnings_label"], value=st.session_state.analyzer_use_earnings)
            st.caption(lang_config["earnings_caption"])
        
        # 模型选择
        st.subheader(lang_config["model_header"])
        model_type = st.selectbox(
            lang_config["model_label"],
            list(config.MODELS.keys()),
            index=list(config.MODELS.keys()).index(st.session_state.analyzer_model),
            format_func=lambda x: config.MODELS[x]
        )
        
        # 分析模式选择
        st.subheader(lang_config["analysis_mode_header"])
        analysis_mode = st.selectbox(
            lang_config["analysis_mode_label"],
            options=["fast_mode", "detailed_mode"],
            index=0 if st.session_state.analyzer_analysis_mode == "fast_mode" else 1,
            format_func=lambda x: lang_config["fast_mode"] if x == "fast_mode" else lang_config["detailed_mode"]
        )
        
        # 显示模式说明
        if analysis_mode == "fast_mode":
            st.caption(lang_config["fast_mode_caption"])
        else:
            st.caption(lang_config["detailed_mode_caption"])
        
        # 付費API設置
        st.subheader(lang_config["api_header"])
        
        # 輸入框
        access_code = st.text_input(
            lang_config["access_code_label"],
            value=st.session_state.get("premium_access_code", ""),
            placeholder=lang_config["access_code_placeholder"]
        )
        
        # 顯示當前狀態
        if st.session_state.get("use_premium_api", False):
            st.success(lang_config["premium_enabled"])
        else:
            st.info(lang_config["free_api"])
        
        # 檢查輸入
        if access_code:
            valid_access_code = get_secret_value("ACCESS_CODE", "")
            if access_code.lower() == valid_access_code.lower():
                if not st.session_state.get("use_premium_api", False):
                    st.session_state.use_premium_api = True
                    st.session_state.premium_access_code = access_code
                    # 当启用付费API时，默认选择2.5 pro模型
                    st.session_state.analyzer_model = "gemini-2.5-pro"
                    st.success(lang_config["premium_success"])
                    st.rerun()
            else:
                st.error(lang_config["access_code_error"])
        
        # 语言选择
        st.subheader(lang_config["language_header"])
        selected_language = st.selectbox(
            lang_config["language_label"],
            options=["English", "中文", "العربية"],
            index=0 if st.session_state.get("selected_language", "English") == "English" else (1 if st.session_state.get("selected_language", "English") == "中文" else 2)
        )
        
        # 如果语言改变，更新session state并重新运行
        if selected_language != st.session_state.get("selected_language", "English"):
            st.session_state.selected_language = selected_language
            st.rerun()
        
        # 调试：清除缓存按钮
        if st.button("🔄 清除应用缓存", help="如果遇到初始化问题，点击此按钮"):
            st.cache_resource.clear()
            st.success("✅ 缓存已清除，页面将重新加载")
            st.rerun()
        
        # 更新session state
        st.session_state.analyzer_ticker = ticker
        st.session_state.analyzer_years = years
        st.session_state.analyzer_use_sec_reports = use_sec_reports
        st.session_state.analyzer_use_sec_others = use_sec_others
        st.session_state.analyzer_use_earnings = use_earnings
        st.session_state.analyzer_model = model_type
        st.session_state.analyzer_analysis_mode = analysis_mode
    
    # 主内容区域

    
    # 显示历史对话和处理状态
    for i, message in enumerate(st.session_state.analyzer_messages):
        with st.chat_message(message["role"], avatar=message.get("avatar")):
            st.markdown(message["content"])
            
            # 如果消息包含文档文件路径，显示原文预览
            if message.get("temp_file_path") and os.path.exists(message["temp_file_path"]):
                file_content = analyzer.document_manager.get_download_content(message["temp_file_path"])
                if file_content:
                    # 解码文件内容
                    content_text = file_content.decode('utf-8')
                    
                    # 使用 expander 来显示原文内容
                    with st.expander("📄 查看原文", expanded=False):
                        # 添加一些样式来改善显示效果
                        st.markdown("---")
                        
                        # 显示文档信息
                        st.caption(f"📋 文档：{message.get('document_title', '未知文档')}")
                        
                        # 使用可滚动的文本区域显示内容，添加唯一key
                        st.text_area(
                            label="原文内容",
                            value=content_text,
                            height=400,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"text_area_{hash(message['temp_file_path'])}"
                        )
                        
                        # 下载按钮
                        filename = f"{message.get('document_title', 'document')}.txt"
                        st.download_button(
                            label="💾 下载原文",
                            data=file_content,
                            file_name=filename,
                            mime="text/plain",
                            key=f"download_{hash(message['temp_file_path'])}",
                            help="下载原文到本地文件"
                        )
        
        # 如果这是最后一条用户消息，并且正在处理，显示状态
        if (message["role"] == "user" and 
            i == len(st.session_state.analyzer_messages) - 1 and 
            analyzer.session_manager.get_processing_status().is_processing):
            
            # 這裡不再顯示status，統一在下方處理
            pass
    
    # 主聊天输入
    if prompt := st.chat_input(lang_config["chat_placeholder"]):
        # 将用户消息添加到历史记录
        st.session_state.analyzer_messages.append({"role": "user", "content": prompt})
        
        # 启动处理流程
        status = analyzer.session_manager.get_processing_status()
        status.is_processing = True
        status.user_question = prompt
        status.processing_step = 1
        status.stop_requested = False  # 重置停止请求
        analyzer.session_manager.update_processing_status(status)
        
        # 关键改动：在这里调用rerun来立即启动处理流程并更新UI
        st.rerun()

    # 在每次重新运行脚本时，检查是否需要处理
    status = analyzer.session_manager.get_processing_status()
    if status.is_processing:
        # 如果正在处理，显示status
        current_step = status.current_status_label or (lang_config.get("processing_status", "Processing..."))
        
        # with st.expander(lang_config["status_header"], expanded=False):
        with st.expander(status.current_status_label, expanded=False):
            st.markdown(f"**{status.current_status_label}**")
            
            if status.total_documents > 0:
                progress_text = lang_config["progress_text"].format(status.completed_documents, status.total_documents)
                # st.progress(status.progress_percentage / 100, text=progress_text)
            
            # 停止按钮
            if st.button(lang_config["stop_button"], key="stop_processing"):
                status.stop_requested = True
                status.is_processing = False
                status.current_status_label = lang_config["stop_success"]
                analyzer.session_manager.update_processing_status(status)
                
                # 添加停止消息到聊天历史
                st.session_state.analyzer_messages.append({
                    "role": "assistant", 
                    "content": lang_config["processing_stopped"],
                    "avatar": "⏹️"
                })
                
                st.rerun()
            
            # 显示文档列表和处理状态
            if status.documents:
                st.markdown("---")
                for idx, doc in enumerate(status.documents):
                    if idx < status.completed_documents:
                        status_icon = "✅"
                    elif idx == status.completed_documents:
                        status_icon = "🔄"
                    else:
                        status_icon = "⏳"
                    
                    # 優化文档标题显示，增加長度限制
                    doc_title = doc.title
                    if len(doc_title) > 80:
                        doc_title = doc_title[:77] + "..."
                    
                    st.markdown(f"{status_icon} {doc_title} ({doc.date})")
            
            # 显示错误消息
            if status.error_message:
                st.error(f"❌ {status.error_message}")
        
        # 将主处理逻辑移到 st.status 中，以提供实时反馈
        process_user_question_new(
            analyzer, ticker, years, 
            st.session_state.analyzer_use_sec_reports,
            st.session_state.analyzer_use_sec_others,
            use_earnings, model_type, st.session_state.analyzer_analysis_mode
        )

def process_user_question_new(analyzer: SECEarningsAnalyzer, ticker: str, years: int, use_sec_reports: bool, use_sec_others: bool, use_earnings: bool, model_type: str, analysis_mode: str = "detailed_mode"):
    """处理用户问题的完整流程 - 新版，带实时状态更新和并行处理"""
    status = analyzer.session_manager.get_processing_status()
    language = st.session_state.get("selected_language", "English")
    
    # 调试参数
    logger.info(f"🔍 [DEBUG] 函数参数: ticker={ticker}, use_sec_reports={use_sec_reports}, use_sec_others={use_sec_others}, use_earnings={use_earnings}")
    
    # 检查对话缓存 - 同一个ticker和years的数据可以复用
    conversation_cache_key = f"conversation_data_{ticker}_{years}_{use_sec_reports}_{use_sec_others}_{use_earnings}"
    cached_documents = analyzer.cache_manager.get(conversation_cache_key)
    
    if cached_documents and len(cached_documents) > 0:
        logger.info(f"🔄 [CACHE] 找到缓存的对话数据: {ticker}, {years}年, 共{len(cached_documents)}个文档")
        # 直接使用缓存的文档，跳过数据获取步骤
        status.documents = cached_documents
        status.total_documents = len(cached_documents)
        
        # 根据分析模式设置正确的处理步骤
        if analysis_mode == "fast_mode":
            status.processing_step = 5  # 快速模式：跳转到快速模式处理
        else:
            status.processing_step = 3  # 详细模式：跳到文档处理步骤
        
        if language == "English":
            status.add_status_message(f"📂 Using cached data: {len(cached_documents)} documents")
            status.current_status_label = f"📂 Using cached conversation data ({len(cached_documents)} documents)"
        else:
            status.add_status_message(f"📂 使用缓存数据: {len(cached_documents)} 个文档")
            status.current_status_label = f"📂 使用缓存的对话数据 ({len(cached_documents)} 个文档)"
        
        analyzer.session_manager.update_processing_status(status)
        logger.info(f"🚀 [CACHE] 跳过数据获取，直接开始处理缓存文档")
    else:
        logger.info(f"🔍 [CACHE] 未找到缓存数据，将重新获取: {conversation_cache_key}")
    
    # 检查是否已请求停止
    if status.stop_requested:
        return
    
    try:
        # 步骤1：分析问题
        if status.processing_step == 1:
            if language == "English":
                status.current_status_label = "🧠 Analyzing your question..."
                status.add_status_message("Started analyzing user question")
                analyzer.session_manager.update_processing_status(status)
                
                status.current_status_label = "🔍 Parsing question content..."
                status.add_status_message("🔍 Parsing question content...")
                analyzer.session_manager.update_processing_status(status)
                
                status.current_status_label = "🤖 Calling AI model for analysis..."
                status.add_status_message("🤖 Calling AI model for analysis...")
                analyzer.session_manager.update_processing_status(status)
            else:
                status.current_status_label = "🧠 正在分析您的问题..."
                status.add_status_message("開始分析用戶問題")
                analyzer.session_manager.update_processing_status(status)
                
                status.current_status_label = "🔍 解析問題內容..."
                status.add_status_message("🔍 解析問題內容...")
                analyzer.session_manager.update_processing_status(status)
                
                status.current_status_label = "🤖 AI is analyzing..."
                status.add_status_message("🤖 AI is analyzing...")
                analyzer.session_manager.update_processing_status(status)
            
            # 创建AI分析状态显示
            ai_analysis_placeholder = st.empty()
            with ai_analysis_placeholder.status("🤖 AI is analyzing...", expanded=True) as ai_analysis_status:
                if language == "English":
                    ai_analysis_status.write("🔍 Parsing question intent...")
                    ai_analysis_status.write(f"📝 Question: {status.user_question}")
                    ai_analysis_status.write(f"📊 Stock: {ticker}")
                    ai_analysis_status.write("🧠 Calling AI model to generate analysis prompts...")
                    ai_analysis_status.write("⏳ Waiting for AI response...")
                else:
                    ai_analysis_status.write("🔍 Parsing question intent...")
                    ai_analysis_status.write(f"📝 Question: {status.user_question}")
                    ai_analysis_status.write(f"📊 Stock: {ticker}")
                    ai_analysis_status.write("🧠 Calling AI model to generate analysis prompts...")
                    ai_analysis_status.write("⏳ Waiting for AI response...")
                
                # 根据分析模式选择不同的处理逻辑
                if analysis_mode == "fast_mode":
                    # 快速模式：生成快速模式提示词
                    fast_mode_prompt = analyzer.generate_fast_mode_prompt(status.user_question, ticker, model_type)
                    status.processing_prompt = fast_mode_prompt
                    status.integration_prompt = ""  # 快速模式不需要integration prompt
                else:
                    # 详细模式：生成详细分析提示词
                    processing_prompt, integration_prompt = analyzer.analyze_question(status.user_question, ticker, model_type)
                    status.processing_prompt = processing_prompt
                    status.integration_prompt = integration_prompt
                
                ai_analysis_status.write("✅ AI分析完成！")
                ai_analysis_status.update(label="✅ 问题分析完成", state="complete")
            
            # 清除AI分析状态显示
            ai_analysis_placeholder.empty()
            
            success_msg = "✅ User question analysis completed" if language == "English" else "✅ 用戶問題分析完成"
            status.add_status_message(success_msg)
            status.processing_step = 2
            analyzer.session_manager.update_processing_status(status)
            time.sleep(0.1) # 短暂停留，让用户看到消息
            st.rerun()
        
        # 步骤2：获取和筛选文档
        elif status.processing_step == 2:
            if status.stop_requested:
                return
                
            if language == "English":
                status.current_status_label = "📂 Retrieving and filtering documents..."
                status.add_status_message("🔍 Started document retrieval")
                analyzer.session_manager.update_processing_status(status)
                
                all_docs = []

                # 定义表单组
                REPORTS_FORMS = ['10-K', '10-Q', '20-F', '6-K', '424B4']
                OTHER_FORMS = ['8-K', 'S-8', 'DEF 14A', 'F-3']
                
                status.add_status_message("📋 Preparing document type filtering...")
                analyzer.session_manager.update_processing_status(status)
                
                selected_forms = []
                if use_sec_reports:
                    selected_forms.extend(REPORTS_FORMS)
                if use_sec_others:
                    selected_forms.extend(OTHER_FORMS)

                # 获取文件 - 根据股票代码类型选择不同的服务
                logger.info(f"🔍 [DEBUG-EN] 股票类型判断: ticker={ticker}, is_hk={is_hk_stock(ticker)}, is_saudi={is_saudi_stock(ticker)}")
                logger.info(f"🔍 [DEBUG-EN] selected_forms: {selected_forms}")
                if selected_forms:
                    if is_hk_stock(ticker):
                        # 港股文件
                        status.current_status_label = "🏢 Connecting to Hong Kong Stock Exchange..."
                        status.add_status_message("🏢 Connecting to Hong Kong Stock Exchange...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 Retrieving Hong Kong stock filings list..."
                        status.add_status_message("📄 Retrieving Hong Kong stock filings list...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        # 将表单类型转换为港股分类
                        hk_forms = []
                        if any(form in REPORTS_FORMS for form in selected_forms):
                            hk_forms.append('quarterly_annual')
                        if any(form in OTHER_FORMS for form in selected_forms):
                            hk_forms.append('others')
                        
                        def hk_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        hk_filings = analyzer.hk_service.get_hk_filings(ticker, years, forms_to_include=hk_forms, status_callback=hk_status_callback)
                        all_docs.extend(hk_filings)
                        status.add_status_message(f"✅ Successfully retrieved {len(hk_filings)} Hong Kong stock filings")
                    elif is_saudi_stock(ticker):
                        # 沙特交易所文件
                        logger.info(f"🔍 [DEBUG-EN] 检测到沙特股票: {ticker}")
                        status.current_status_label = "🇸🇦 Connecting to Saudi Exchange..."
                        status.add_status_message("🇸🇦 Connecting to Saudi Exchange...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 Retrieving Saudi Exchange announcements..."
                        status.add_status_message("📄 Retrieving Saudi Exchange announcements...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        def saudi_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        saudi_filings = analyzer.saudi_service.get_saudi_filings(ticker, years, status_callback=saudi_status_callback)
                        logger.info(f"🔍 [DEBUG-EN] saudi_filings 返回结果: 类型={type(saudi_filings)}, 长度={len(saudi_filings) if saudi_filings else 'None'}")
                        if saudi_filings:
                            for i, doc in enumerate(saudi_filings[:3]):  # 只显示前3个
                                logger.info(f"🔍 [DEBUG-EN] saudi_filings[{i}]: {doc.title}, 类型={doc.type}, 日期={doc.date}")
                        all_docs.extend(saudi_filings)
                        logger.info(f"🔍 [DEBUG-EN] all_docs.extend后: all_docs长度={len(all_docs)}")
                        status.add_status_message(f"✅ Successfully retrieved {len(saudi_filings)} Saudi Exchange announcements")
                    else:
                        # 美股SEC文件
                        status.current_status_label = "🇺🇸 Connecting to SEC database..."
                        status.add_status_message("🇺🇸 Connecting to SEC database...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 Retrieving SEC filings list..."
                        status.add_status_message("📄 Retrieving SEC filings list...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        def sec_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        sec_filings = analyzer.sec_service.get_filings(ticker, years, forms_to_include=selected_forms, status_callback=sec_status_callback)
                        all_docs.extend(sec_filings)
                        status.add_status_message(f"✅ Successfully retrieved {len(sec_filings)} SEC filings")
                
                # 获取财报记录 - 支持美股和港股
                if use_earnings:
                    status.current_status_label = "🎙️ Connecting to earnings call transcript service..."
                    status.add_status_message("🎙️ Connecting to earnings call transcript service...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    status.current_status_label = "📋 Retrieving available earnings call list..."
                    status.add_status_message("📋 Retrieving available earnings call list...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    all_earnings_urls = analyzer.earnings_service.get_available_quarters(ticker)
                    
                    # 修正年份计算逻辑：与SEC保持一致
                    current_year = datetime.now().year
                    cutoff_date = datetime(current_year - years + 1, 1, 1).date()  # 往前推years年
                    status.add_status_message(f"⏰ Started retrieving earnings calls and filtering by cutoff date ({cutoff_date})...")
                    analyzer.session_manager.update_processing_status(status)

                    filtered_earnings_docs = []
                    
                    # 使用并行处理来提升速度
                    status.add_status_message("📄 Starting parallel processing of earnings calls...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    # 创建earnings获取状态显示
                    earnings_status_placeholder = st.empty()
                    with earnings_status_placeholder.status("🎙️ Retrieving earnings call transcripts...", expanded=True) as earnings_status:
                        earnings_status.write(f"📋 Found {len(all_earnings_urls)} available earnings calls")
                        earnings_status.write(f"📅 Filtering by cutoff date: {cutoff_date}")
                        earnings_status.write("🔄 Starting batch processing...")
                        
                        # 分批处理以避免过多并发请求
                        batch_size = 1  # 每批处理1个
                        for batch_start in range(0, len(all_earnings_urls), batch_size):
                            if status.stop_requested:
                                break
                                
                            batch_end = min(batch_start + batch_size, len(all_earnings_urls))
                            batch_urls = all_earnings_urls[batch_start:batch_end]
                            
                            status.add_status_message(f"📄 Processing batch {batch_start//batch_size + 1}/{(len(all_earnings_urls) + batch_size - 1)//batch_size} ({batch_start + 1}-{batch_end}/{len(all_earnings_urls)})")
                            analyzer.session_manager.update_processing_status(status)
                            
                            # 显示当前批次正在处理的earnings
                            earnings_status.write(f"📦 Processing batch {batch_start//batch_size + 1}/{(len(all_earnings_urls) + batch_size - 1)//batch_size}")
                            
                            # 显示当前批次的具体项目
                            for url_path in batch_urls:
                                parsed_info = analyzer.earnings_service.parse_transcript_url(url_path)
                                if parsed_info:
                                    _ticker, year, quarter = parsed_info
                                    earnings_status.write(f"⏳ 开始获取: {_ticker} {year} Q{quarter}")
                            
                            # 顺序处理当前批次
                            batch_results = analyzer.earnings_service.get_earnings_transcript_batch(batch_urls, max_workers=1)
                            
                            # 处理批次结果
                            for i, (url_path, transcript_info) in enumerate(zip(batch_urls, batch_results)):
                                if status.stop_requested:
                                    break
                                    
                                parsed_info = analyzer.earnings_service.parse_transcript_url(url_path)
                                if parsed_info:
                                    _ticker, year, quarter = parsed_info
                                    
                                    if transcript_info and transcript_info.get('parsed_successfully'):
                                        real_date = transcript_info.get('date')
                                        if real_date:
                                            if real_date >= cutoff_date:
                                                doc = Document(
                                                    type='Earnings Call',
                                                    title=f"{transcript_info['ticker']} {transcript_info['year']} Q{transcript_info['quarter']} Earnings Call",
                                                    date=real_date, url=url_path, content=transcript_info.get('content'),
                                                    year=transcript_info.get('year'), quarter=transcript_info.get('quarter')
                                                )
                                                filtered_earnings_docs.append(doc)
                                                earnings_status.write(f"✅ 成功获取: {_ticker} {year} Q{quarter} ({real_date})")
                                            else:
                                                earnings_status.write(f"⏹️ 日期过早，停止获取: {_ticker} {year} Q{quarter} ({real_date})")
                                                status.add_status_message(f"Earnings call date {real_date} is earlier than cutoff date, stopping retrieval")
                                                time.sleep(0.1)
                                                break
                                    else:
                                        earnings_status.write(f"⚠️ 获取失败: {_ticker} {year} Q{quarter}")
                                        logger.warning(f"Failed to retrieve or parse earnings call, skipping: {_ticker} {year} Q{quarter}")
                            
                            # 如果发现日期过早，停止处理
                            if batch_results and any(
                                result and result.get('parsed_successfully') and 
                                result.get('date') and result.get('date') < cutoff_date 
                                for result in batch_results
                            ):
                                break
                        
                        earnings_status.write(f"✅ 完成！共获取 {len(filtered_earnings_docs)} 个有效的财报记录")
                        earnings_status.update(label="✅ Earnings call retrieval completed", state="complete")
                    
                    # 清除earnings状态显示
                    earnings_status_placeholder.empty()
                    
                    all_docs.extend(filtered_earnings_docs)
                    status.add_status_message(f"✅ Successfully filtered {len(filtered_earnings_docs)} relevant earnings calls")
                    analyzer.session_manager.update_processing_status(status)

                status.add_status_message("📊 Organizing document list...")
                analyzer.session_manager.update_processing_status(status)
                
                all_docs.sort(key=lambda x: x.date, reverse=True)
                
                # 沙特交易所文档并发下载内容
                saudi_docs = [doc for doc in all_docs if doc.type == 'Saudi Exchange Filing']
                if saudi_docs:
                    status.add_status_message(f"🚀 Pre-downloading {len(saudi_docs)} Saudi Exchange documents...")
                    analyzer.session_manager.update_processing_status(status)
                    logger.info(f"🚀 [SAUDI-BATCH] 开始预下载 {len(saudi_docs)} 个沙特文档")
                    
                    # 创建沙特下载状态显示
                    saudi_download_placeholder = st.empty()
                    
                    def saudi_status_callback(message, completed, total):
                        with saudi_download_placeholder.container():
                            st.info(f"🇸🇦 **Saudi Exchange Download Status**")
                            st.progress(completed / total if total > 0 else 0)
                            st.write(f"{message}")
                            st.write(f"Progress: {completed}/{total}")
                    
                    # 使用批量下载
                    all_docs = analyzer.saudi_service.download_saudi_filings_batch(
                        all_docs, 
                        max_workers=5, 
                        status_callback=saudi_status_callback
                    )
                    
                    # 清除下载状态显示
                    saudi_download_placeholder.empty()
                    
                    status.add_status_message(f"✅ Saudi Exchange documents pre-downloaded")
                    analyzer.session_manager.update_processing_status(status)
                
                status.documents = all_docs
                status.update_progress(0, len(all_docs), "Document list ready")
                status.add_status_message(f"✅ Document list ready, total {len(all_docs)} documents")
                
                # 缓存对话数据 - 供后续对话复用
                analyzer.cache_manager.set(conversation_cache_key, all_docs)
                logger.info(f"💾 [CACHE] 已缓存对话数据: {conversation_cache_key}, 共{len(all_docs)}个文档")
                
                # 调试日志：显示文档类型分布
                doc_types = {}
                for doc in all_docs:
                    doc_type = doc.type
                    doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
                logger.info(f"📊 [DEBUG] 文档类型分布: {doc_types}")
                logger.info(f"📊 [DEBUG] 设置status.documents，总数: {len(all_docs)}")
                
                # 根据分析模式选择不同的处理步骤
                if analysis_mode == "fast_mode":
                    status.processing_step = 5  # 跳转到快速模式处理
                else:
                    status.processing_step = 3  # 详细模式：逐个处理文档
                analyzer.session_manager.update_processing_status(status)
            
            else:
                # 中文版本的消息
                status.current_status_label = "📂 正在检索和筛选文档..."
                status.add_status_message("🔍 開始檢索文檔")
                analyzer.session_manager.update_processing_status(status)
                
                all_docs = []

                # 定义表单组
                REPORTS_FORMS = ['10-K', '10-Q', '20-F', '6-K', '424B4']
                OTHER_FORMS = ['8-K', 'S-8', 'DEF 14A', 'F-3']
                
                status.add_status_message("📋 準備文檔類型篩選...")
                analyzer.session_manager.update_processing_status(status)
                
                selected_forms = []
                if use_sec_reports:
                    selected_forms.extend(REPORTS_FORMS)
                if use_sec_others:
                    selected_forms.extend(OTHER_FORMS)

                # 获取文件 - 根据股票代码类型选择不同的服务
                if selected_forms:
                    if is_hk_stock(ticker):
                        # 港股文件
                        status.current_status_label = "🏢 正在連接港股交易所..."
                        status.add_status_message("🏢 正在連接港股交易所...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 正在获取港股文件列表..."
                        status.add_status_message("📄 正在获取港股文件列表...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        # 将表单类型转换为港股分类
                        hk_forms = []
                        if any(form in REPORTS_FORMS for form in selected_forms):
                            hk_forms.append('quarterly_annual')
                        if any(form in OTHER_FORMS for form in selected_forms):
                            hk_forms.append('others')
                        
                        def hk_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        hk_filings = analyzer.hk_service.get_hk_filings(ticker, years, forms_to_include=hk_forms, status_callback=hk_status_callback)
                        all_docs.extend(hk_filings)
                        status.add_status_message(f"✅ 成功获取 {len(hk_filings)} 份港股文件")
                    elif is_saudi_stock(ticker):
                        # 沙特交易所文件
                        status.current_status_label = "🇸🇦 正在連接沙特交易所..."
                        status.add_status_message("🇸🇦 正在連接沙特交易所...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 正在获取沙特交易所公告..."
                        status.add_status_message("📄 正在获取沙特交易所公告...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        def saudi_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        saudi_filings = analyzer.saudi_service.get_saudi_filings(ticker, years, status_callback=saudi_status_callback)
                        all_docs.extend(saudi_filings)
                        status.add_status_message(f"✅ 成功获取 {len(saudi_filings)} 份沙特交易所公告")
                    else:
                        # 美股SEC文件
                        status.current_status_label = "🇺🇸 正在連接SEC數據庫..."
                        status.add_status_message("🇺🇸 正在連接SEC數據庫...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        status.current_status_label = "📄 正在获取SEC文件列表..."
                        status.add_status_message("📄 正在获取SEC文件列表...")
                        analyzer.session_manager.update_processing_status(status)
                        
                        def sec_status_callback(msg):
                            status.add_status_message(msg)
                            analyzer.session_manager.update_processing_status(status)
                        
                        sec_filings = analyzer.sec_service.get_filings(ticker, years, forms_to_include=selected_forms, status_callback=sec_status_callback)
                        all_docs.extend(sec_filings)
                        status.add_status_message(f"✅ 成功获取 {len(sec_filings)} 份SEC文件")
                
                # 获取财报记录 - 支持美股和港股
                if use_earnings:
                    status.current_status_label = "🎙️ 正在連接財報會議記錄服務..."
                    status.add_status_message("🎙️ 正在連接財報會議記錄服務...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    status.current_status_label = "📋 正在获取可用财报列表..."
                    status.add_status_message("📋 正在获取可用财报列表...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    all_earnings_urls = analyzer.earnings_service.get_available_quarters(ticker)
                    
                    # 修正年份计算逻辑：与SEC保持一致
                    current_year = datetime.now().year
                    cutoff_date = datetime(current_year - years + 1, 1, 1).date()  # 往前推years年
                    status.add_status_message(f"⏰ 開始逐一获取财报並按截止日期 ({cutoff_date}) 篩選...")
                    analyzer.session_manager.update_processing_status(status)

                    filtered_earnings_docs = []
                    
                    # 使用并行处理来提升速度
                    status.add_status_message("📄 开始并行处理财报记录...")
                    analyzer.session_manager.update_processing_status(status)
                    
                    # 创建earnings获取状态显示
                    earnings_status_placeholder = st.empty()
                    with earnings_status_placeholder.status("🎙️ 正在获取财报会议记录...", expanded=True) as earnings_status:
                        earnings_status.write(f"📋 找到 {len(all_earnings_urls)} 个可用的财报记录")
                        earnings_status.write(f"📅 按截止日期筛选: {cutoff_date}")
                        earnings_status.write("🔄 开始批量处理...")
                        
                        # 分批处理以避免过多并发请求
                        batch_size = 2  # 每批处理2个
                        for batch_start in range(0, len(all_earnings_urls), batch_size):
                            if status.stop_requested:
                                break
                                
                            batch_end = min(batch_start + batch_size, len(all_earnings_urls))
                            batch_urls = all_earnings_urls[batch_start:batch_end]
                            
                            status.add_status_message(f"📄 处理批次 {batch_start//batch_size + 1}/{(len(all_earnings_urls) + batch_size - 1)//batch_size} ({batch_start + 1}-{batch_end}/{len(all_earnings_urls)})")
                            analyzer.session_manager.update_processing_status(status)
                            
                            # 显示当前批次正在处理的earnings
                            earnings_status.write(f"📦 处理批次 {batch_start//batch_size + 1}/{(len(all_earnings_urls) + batch_size - 1)//batch_size}")
                            
                            # 显示当前批次的具体项目
                            for url_path in batch_urls:
                                parsed_info = analyzer.earnings_service.parse_transcript_url(url_path)
                                if parsed_info:
                                    _ticker, year, quarter = parsed_info
                                    earnings_status.write(f"⏳ 开始获取: {_ticker} {year} Q{quarter}")
                            
                            # 顺序处理当前批次
                            batch_results = analyzer.earnings_service.get_earnings_transcript_batch(batch_urls, max_workers=1)
                            
                            # 处理批次结果
                            for i, (url_path, transcript_info) in enumerate(zip(batch_urls, batch_results)):
                                if status.stop_requested:
                                    break
                                    
                                parsed_info = analyzer.earnings_service.parse_transcript_url(url_path)
                                if parsed_info:
                                    _ticker, year, quarter = parsed_info
                                    
                                    if transcript_info and transcript_info.get('parsed_successfully'):
                                        real_date = transcript_info.get('date')
                                        if real_date:
                                            if real_date >= cutoff_date:
                                                doc = Document(
                                                    type='Earnings Call',
                                                    title=f"{transcript_info['ticker']} {transcript_info['year']} Q{transcript_info['quarter']} Earnings Call",
                                                    date=real_date, url=url_path, content=transcript_info.get('content'),
                                                    year=transcript_info.get('year'), quarter=transcript_info.get('quarter')
                                                )
                                                filtered_earnings_docs.append(doc)
                                                earnings_status.write(f"✅ 成功获取: {_ticker} {year} Q{quarter} ({real_date})")
                                            else:
                                                earnings_status.write(f"⏹️ 日期过早，停止获取: {_ticker} {year} Q{quarter} ({real_date})")
                                                status.add_status_message(f"财报日期 {real_date} 早于截止日期，停止获取")
                                                time.sleep(0.1)
                                                break
                                    else:
                                        earnings_status.write(f"⚠️ 获取失败: {_ticker} {year} Q{quarter}")
                                        logger.warning(f"获取或解析财报失败，跳过: {_ticker} {year} Q{quarter}")
                            
                            # 如果发现日期过早，停止处理
                            if batch_results and any(
                                result and result.get('parsed_successfully') and 
                                result.get('date') and result.get('date') < cutoff_date 
                                for result in batch_results
                            ):
                                break
                        
                        earnings_status.write(f"✅ 完成！共获取 {len(filtered_earnings_docs)} 个有效的财报记录")
                        earnings_status.update(label="✅ 财报记录获取完成", state="complete")
                    
                    # 清除earnings状态显示
                    earnings_status_placeholder.empty()
                    
                    all_docs.extend(filtered_earnings_docs)
                    status.add_status_message(f"✅ 成功筛选出 {len(filtered_earnings_docs)} 份相关财报")
                    analyzer.session_manager.update_processing_status(status)

                status.add_status_message("📊 正在整理文檔列表...")
                analyzer.session_manager.update_processing_status(status)
                
                all_docs.sort(key=lambda x: x.date, reverse=True)
                
                # 沙特交易所文档并发下载内容
                saudi_docs = [doc for doc in all_docs if doc.type == 'Saudi Exchange Filing']
                if saudi_docs:
                    status.add_status_message(f"🚀 预下载 {len(saudi_docs)} 个沙特交易所文档...")
                    analyzer.session_manager.update_processing_status(status)
                    logger.info(f"🚀 [SAUDI-BATCH] 开始预下载 {len(saudi_docs)} 个沙特文档")
                    
                    # 创建沙特下载状态显示
                    saudi_download_placeholder = st.empty()
                    
                    def saudi_status_callback_cn(message, completed, total):
                        current_language = st.session_state.get("selected_language", "English")
                        with saudi_download_placeholder.container():
                            if current_language == "العربية":
                                st.info(f"🇸🇦 **حالة تحميل السوق السعودية**")
                                st.progress(completed / total if total > 0 else 0)
                                st.write(f"{message}")
                                st.write(f"التقدم: {completed}/{total}")
                            else:
                                st.info(f"🇸🇦 **Saudi Exchange Download Status**")
                                st.progress(completed / total if total > 0 else 0)
                                st.write(f"{message}")
                                st.write(f"Progress: {completed}/{total}")
                    
                    # 使用批量下载
                    all_docs = analyzer.saudi_service.download_saudi_filings_batch(
                        all_docs, 
                        max_workers=5, 
                        status_callback=saudi_status_callback_cn
                    )
                    
                    # 清除下载状态显示
                    saudi_download_placeholder.empty()
                    
                    status.add_status_message(f"✅ 沙特交易所文档预下载完成")
                    analyzer.session_manager.update_processing_status(status)
                
                status.documents = all_docs
                status.update_progress(0, len(all_docs), "AI is thinking...")
                status.add_status_message(f"✅ 文档列表准备就绪，共 {len(all_docs)} 份")
                
                # 缓存对话数据 - 供后续对话复用
                analyzer.cache_manager.set(conversation_cache_key, all_docs)
                logger.info(f"💾 [CACHE] 已缓存对话数据: {conversation_cache_key}, 共{len(all_docs)}个文档")
                
                # 调试日志：显示文档类型分布
                doc_types = {}
                for doc in all_docs:
                    doc_type = doc.type
                    doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
                logger.info(f"📊 [DEBUG-CN] 文档类型分布: {doc_types}")
                logger.info(f"📊 [DEBUG-CN] 设置status.documents，总数: {len(all_docs)}")
                
                # 根据分析模式选择不同的处理步骤
                if analysis_mode == "fast_mode":
                    status.processing_step = 5  # 跳转到快速模式处理
                else:
                    status.processing_step = 3  # 详细模式：逐个处理文档
                analyzer.session_manager.update_processing_status(status)

            st.rerun()

        # 步骤3：按日期顺序处理文档
        elif status.processing_step == 3:
            if status.stop_requested:
                return
                
            docs_to_process = status.documents
            
            # 初始化处理状态
            if status.completed_documents == 0:
                status.document_results = []
            
            # 检查是否还有文档需要处理
            if status.completed_documents < len(docs_to_process):
                current_doc = docs_to_process[status.completed_documents]
                
                # 更新状态
                analyzing_msg = f"正在分析: {current_doc.title}" if language == "中文" else f"Analyzing: {current_doc.title}"
                status.add_status_message(analyzing_msg)
                
                progress_label = f"📖 分析文档中... {status.completed_documents + 1}/{len(docs_to_process)}" if language == "中文" else f"📖 Analyzing document {status.completed_documents + 1}/{len(docs_to_process)}"
                status.update_progress(status.completed_documents, len(docs_to_process), progress_label)
                analyzer.session_manager.update_processing_status(status)
                
                try:
                    # 特殊处理6-K文件
                    if hasattr(current_doc, 'form_type') and current_doc.form_type == '6-K':
                        sixk_msg = f"检测到6-K文件，开始处理附件" if language == "中文" else f"Detected 6-K file, starting to process attachments"
                        status.add_status_message(sixk_msg)
                        
                        # 初始化6-K处理器
                        analyzer.sec_service._init_sixk_processor(analyzer.document_manager.temp_dir)
                        
                        # 从URL中提取ticker和cik
                        ticker = st.session_state.analyzer_ticker
                        
                        # 获取CIK
                        ticker_map = analyzer.sec_service.get_cik_map()
                        cik = ticker_map.get(ticker.upper(), '')
                        
                        logger.info(f"🔍 [6K-MAIN] 准备处理6-K文件: {current_doc.title}")
                        logger.info(f"🔍 [6K-MAIN] Ticker: {ticker}, CIK: {cik}")
                        logger.info(f"🔍 [6K-MAIN] 6-K URL: {current_doc.url}")
                        
                        downloading_msg = f"正在下载和处理6-K附件..." if language == "中文" else f"Downloading and processing 6-K attachments..."
                        status.add_status_message(downloading_msg)
                        analyzer.session_manager.update_processing_status(status)
                        
                        # 处理6-K文件
                        logger.info(f"🔍 [6K-MAIN] 开始调用SixKProcessor.process_6k_filing...")
                        processed_docs = analyzer.sec_service.sixk_processor.process_6k_filing(
                            ticker, cik, current_doc.url, current_doc
                        )
                        logger.info(f"🔍 [6K-MAIN] SixKProcessor.process_6k_filing返回结果: {len(processed_docs)} 个文档")
                        
                        if processed_docs:
                            for i, doc in enumerate(processed_docs):
                                logger.info(f"🔍 [6K-MAIN] 返回文档{i+1}: {doc.title}, 内容长度: {len(doc.content) if doc.content else 0}")
                        else:
                            logger.info(f"ℹ️ [6K-MAIN] SixKProcessor没有返回任何文档，这意味着没有找到ex99附件")
                        
                        completed_msg = f"6-K处理完成，生成了 {len(processed_docs)} 个分析文档" if language == "中文" else f"6-K processing completed, generated {len(processed_docs)} analysis documents"
                        status.add_status_message(completed_msg)
                        
                        # 检查是否需要对6-K文件进行分类过滤
                        should_filter_6k = (st.session_state.analyzer_use_sec_reports and 
                                           not st.session_state.analyzer_use_sec_others)
                        
                        # 处理所有6-K相关文档
                        for i, doc in enumerate(processed_docs):
                            if status.stop_requested:
                                break
                                
                            analyzing_6k_msg = f"正在分析第 {i+1}/{len(processed_docs)} 个6-K文档: {doc.title}" if language == "中文" else f"Analyzing {i+1}/{len(processed_docs)} 6-K document: {doc.title}"
                            status.add_status_message(analyzing_6k_msg)
                            analyzer.session_manager.update_processing_status(status)
                            
                            # 如果需要过滤6-K文件，先用便宜模型进行分类
                            if should_filter_6k:
                                classifying_msg = f"正在分类6-K文档..." if language == "中文" else f"Classifying 6-K document..."
                                status.add_status_message(classifying_msg)
                                
                                # 确保文档有内容
                                if not doc.content:
                                    if doc.type == 'SEC Filing':
                                        doc.content = analyzer.sec_service.download_filing(doc.url)
                                
                                # 使用便宜模型进行分类
                                is_quarterly_annual_ipo = analyzer.gemini_service.classify_6k_document(doc.content)
                                
                                if not is_quarterly_annual_ipo:
                                    # 如果不是季报/年报/IPO，跳过这个文档
                                    skip_msg = f"跳过非季报/年报/IPO的6-K文档: {doc.title}" if language == "中文" else f"Skipping non-quarterly/annual/IPO 6-K document: {doc.title}"
                                    status.add_status_message(skip_msg)
                                    continue
                                else:
                                    # 如果是季报/年报/IPO，继续处理
                                    continue_msg = f"检测到季报/年报/IPO文档，继续分析: {doc.title}" if language == "中文" else f"Detected quarterly/annual/IPO document, continuing analysis: {doc.title}"
                                    status.add_status_message(continue_msg)
                            
                            # 创建AI分析状态显示
                            ai_status_placeholder = st.empty()
                            with ai_status_placeholder.status(f"🤖 AI正在分析6-K文档 {i+1}/{len(processed_docs)}...", expanded=True) as ai_status:
                                ai_status.write(f"📄 正在分析: {doc.title}")
                                ai_status.write("📝 正在构建分析提示词...")
                                ai_status.write("🧠 正在调用AI模型进行深度分析...")
                                ai_status.write("⏳ 开始流式响应...")
                                
                                # 执行实际的AI分析 - 使用流式响应
                                stream_generator = analyzer.process_document_stream(doc, status.processing_prompt, model_type)
                                
                                ai_status.write("✅ AI分析开始！")
                                ai_status.update(label=f"✅ 6-K文档 {i+1}/{len(processed_docs)} 分析开始", state="complete")
                            
                            # 清除AI状态显示
                            ai_status_placeholder.empty()
                            
                            # 显示文档标题
                            st.markdown(f"### 📅 {doc.date}")
                            st.markdown(f"### {doc.title}")
                            
                            # 使用流式响应显示结果
                            analysis_result = st.write_stream(stream_generator)
                            
                            # 根据文档类型设置头像
                            avatar = "📄"
                            
                            # 保存文档内容到临时文件
                            temp_file_path = analyzer.document_manager.save_document_content(doc)
                            
                            # 将分析结果添加到聊天历史中，这样rerun时不会丢失
                            message_content = f"### 📅 {doc.date}\n### {doc.title}\n\n{analysis_result}"
                            st.session_state.analyzer_messages.append({
                                "role": "assistant",
                                "content": message_content,
                                "avatar": avatar,
                                "temp_file_path": temp_file_path,
                                "document_title": doc.title
                            })
                            
                            # 保存结果
                            status.document_results.append({
                                "title": doc.title,
                                "date": doc.date.isoformat(),
                                "analysis": analysis_result
                            })
                            
                            completed_6k_msg = f"完成第 {i+1} 个6-K文档分析" if language == "中文" else f"Completed {i+1} 6-K document analysis"
                            status.add_status_message(completed_6k_msg)
                    else:
                        # 普通文档处理
                        # 创建AI分析状态显示
                        ai_status_placeholder = st.empty()
                        with ai_status_placeholder.status("🤖 AI正在分析文档内容...", expanded=True) as ai_status:
                            # 显示详细的AI分析步骤
                            ai_status.write("📄 正在准备文档内容...")
                            
                            # 检查文档内容是否需要下载
                            if not current_doc.content:
                                ai_status.write("📥 正在下载文档内容...")
                                if current_doc.type == 'SEC Filing':
                                    if hasattr(current_doc, 'form_type') and current_doc.form_type == '6-K':
                                        ai_status.write("⚠️ 6-K文件内容处理失败")
                                    else:
                                        ai_status.write("🔗 正在从SEC EDGAR下载文档...")
                                elif current_doc.type == 'HK Stock Filing':
                                    ai_status.write("🔗 正在从港交所下载文档...")
                                elif current_doc.type == 'Earnings Call':
                                    ai_status.write("🔗 正在获取财报会议记录...")
                            
                            ai_status.write("📝 正在构建分析提示词...")
                            ai_status.write("🧠 正在调用AI模型进行深度分析...")
                            ai_status.write("⏳ 开始流式响应...")
                            
                            # 执行实际的AI分析 - 使用流式响应
                            stream_generator = analyzer.process_document_stream(current_doc, status.processing_prompt, model_type)
                            
                            ai_status.write("✅ AI分析开始！")
                            ai_status.update(label="✅ AI分析开始", state="complete")
                        
                        # 清除AI状态显示
                        ai_status_placeholder.empty()
                        
                        # 显示文档标题
                        st.markdown(f"### 📅 {current_doc.date}")
                        st.markdown(f"### {current_doc.title}")
                        
                        # 使用流式响应显示结果
                        analysis_result = st.write_stream(stream_generator)
                        
                        # 根据文档类型设置头像
                        if current_doc.type == 'SEC Filing':
                            avatar = "📄"
                        elif current_doc.type == 'HK Stock Filing':
                            avatar = "🏢"
                        elif current_doc.type == 'Earnings Call':
                            avatar = "🎙️"
                        else:
                            avatar = "📄"
                        
                        # 保存文档内容到临时文件
                        temp_file_path = analyzer.document_manager.save_document_content(current_doc)
                        
                        # 将分析结果添加到聊天历史中，这样rerun时不会丢失
                        message_content = f"### 📅 {current_doc.date}\n### {current_doc.title}\n\n{analysis_result}"
                        st.session_state.analyzer_messages.append({
                            "role": "assistant",
                            "content": message_content,
                            "avatar": avatar,
                            "temp_file_path": temp_file_path,
                            "document_title": current_doc.title
                        })
                        
                        # 保存结果
                        status.document_results.append({
                            "title": current_doc.title,
                            "date": current_doc.date.isoformat(),
                            "analysis": analysis_result
                        })
                    
                    status.completed_documents += 1
                    
                    # 更新状态
                    analyzer.session_manager.update_processing_status(status)
                    
                    # 如果还有更多文档需要处理，继续下一个
                    if status.completed_documents < len(docs_to_process) and not status.stop_requested:
                        st.rerun()
                    else:
                        # 所有文档处理完成，进入下一步
                        status.processing_step = 4
                        analyzer.session_manager.update_processing_status(status)
                        st.rerun()
                    
                except Exception as exc:
                    failed_msg = f"分析失败: {current_doc.title} - {exc}" if language == "中文" else f"Analysis failed: {current_doc.title} - {exc}"
                    status.add_status_message(failed_msg)
                    logger.error(f"文档分析失败: {current_doc.title} - {exc}")
                    
                    # 也将错误信息添加到聊天历史中
                    error_prefix = f"**⚠️ {current_doc.title} 分析失败:**" if language == "中文" else f"**⚠️ {current_doc.title} Analysis Failed:**"
                    error_message = f"{error_prefix}\n\n{exc}"
                    st.session_state.analyzer_messages.append({
                        "role": "assistant", 
                        "content": error_message,
                        "avatar": "⚠️"
                    })
                    
                    # 跳过失败的文档，继续处理下一个
                    status.completed_documents += 1
                    analyzer.session_manager.update_processing_status(status)
                    st.rerun()
            else:
                # 所有文档处理完成
                all_completed_msg = "✅ 所有文档分析完成" if language == "中文" else "✅ All document analysis completed"
                status.current_status_label = all_completed_msg
                status.processing_step = 4
                analyzer.session_manager.update_processing_status(status)
                st.rerun()
        
        # 步骤4：整合结果
        elif status.processing_step == 4:
            if status.stop_requested:
                return
                
            generating_msg = "📊 正在生成最终报告..." if language == "中文" else "📊 Generating final report..."
            status.current_status_label = generating_msg
            
            integrating_msg = "整合所有分析结果..." if language == "中文" else "Integrating all analysis results..."
            status.add_status_message(integrating_msg)
            analyzer.session_manager.update_processing_status(status)
            
            # 过滤掉失败的结果
            successful_results = [res for res in status.document_results if res is not None]
            
            # 显示综合报告标题
            st.markdown("### 📊 Summary")
            
            # 使用流式响应显示最终报告
            final_report_stream = analyzer.integrate_results_stream(
                successful_results, status.integration_prompt, status.user_question, ticker, model_type
            )
            final_report = st.write_stream(final_report_stream)
            
            # 将综合报告添加到聊天历史中
            summary_content = f"### 📊 Summary\n\n{final_report}"
            st.session_state.analyzer_messages.append({
                "role": "assistant",
                "content": summary_content,
                "avatar": "📊"
            })
            
            report_completed_msg = "综合报告生成完毕！" if language == "中文" else "Comprehensive report generated!"
            status.add_status_message(report_completed_msg)
            
            processing_completed_msg = "✅ 处理完成！" if language == "中文" else "✅ Processing completed!"
            status.current_status_label = processing_completed_msg
            status.progress_percentage = 100.0
            analyzer.session_manager.update_processing_status(status)
            
            # 短暂显示完成状态
            time.sleep(0.1)
            
            # 重置状态
            status = ProcessingStatus()
            analyzer.session_manager.update_processing_status(status)

            st.rerun()
        
        # 步骤5：快速模式处理
        elif status.processing_step == 5:
            if status.stop_requested:
                return
                
            generating_msg = "⚡ 正在快速分析所有文档..." if language == "中文" else "⚡ Fast analyzing all documents..."
            status.current_status_label = generating_msg
            status.add_status_message(generating_msg)
            analyzer.session_manager.update_processing_status(status)
            
            # 生成快速模式提示词
            fast_mode_prompt = analyzer.generate_fast_mode_prompt(status.user_question, ticker, model_type)
            
            # 创建AI分析状态显示
            ai_status_placeholder = st.empty()
            with ai_status_placeholder.status("⚡ 快速模式AI分析中...", expanded=True) as ai_status:
                ai_status.write(f"📊 正在同时分析 {len(status.documents)} 个文档")
                ai_status.write("🧠 正在调用AI模型进行综合分析...")
                
                # 执行快速模式分析
                fast_stream = analyzer.process_all_documents_fast(status.documents, fast_mode_prompt, model_type)
                
                ai_status.write("✅ 快速分析准备完成！")
                ai_status.update(label="✅ 快速分析准备完成", state="complete")
            
            # 清除AI状态显示
            ai_status_placeholder.empty()
            
            # 显示快速分析结果
            st.markdown("### ⚡ 快速分析结果" if language == "中文" else "### ⚡ Fast Analysis Results")
            
            # 添加AI思考状态
            thinking_placeholder = st.empty()
            if language == "English":
                thinking_msg = "🤖 AI is thinking now..."
            elif language == "العربية":
                thinking_msg = "🤖 الذكاء الاصطناعي يفكر الآن..."
            else:
                thinking_msg = "🤖 AI正在思考中..."
            thinking_placeholder.info(thinking_msg)
            
            # 使用流式响应显示结果
            final_result = st.write_stream(fast_stream)
            
            # 清除思考状态
            thinking_placeholder.empty()
            
            # 将结果添加到聊天历史中
            result_content = f"### ⚡ {'快速分析结果' if language == '中文' else 'Fast Analysis Results'}\n\n{final_result}"
            st.session_state.analyzer_messages.append({
                "role": "assistant",
                "content": result_content,
                "avatar": "⚡"
            })
            
            # 完成处理
            completed_msg = "快速分析完成！" if language == "中文" else "Fast analysis completed!"
            status.add_status_message(completed_msg)
            
            processing_completed_msg = "✅ 处理完成！" if language == "中文" else "✅ Processing completed!"
            status.current_status_label = processing_completed_msg
            status.progress_percentage = 100.0
            analyzer.session_manager.update_processing_status(status)
            
            # 短暂显示完成状态
            time.sleep(0.1)
            
            # 重置状态
            status = ProcessingStatus()
            analyzer.session_manager.update_processing_status(status)
            
            st.rerun()

    except Exception as e:
        logger.error(f"处理流程出错: {e}", exc_info=True)
        error_msg = f"处理过程中出现严重错误: {e}" if language == "中文" else f"A serious error occurred during processing: {e}"
        st.error(error_msg)
        # 重置状态
        status = ProcessingStatus()
        analyzer.session_manager.update_processing_status(status)
        st.rerun()


def process_user_question(analyzer: SECEarningsAnalyzer, ticker: str, years: int, use_sec: bool, use_earnings: bool, model_type: str):
    """处理用户问题的完整流程"""
    # DEPRECATED: use process_user_question_new instead
    pass

if __name__ == "__main__":
    main() 