import streamlit as st
import fitz  # PyMuPDF
import io
import base64
from PIL import Image
from google import genai
from google.genai import types
from itertools import cycle
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import math
import re
from streamlit_pdf_viewer import pdf_viewer

# 页面配置
st.set_page_config(
    page_title="Document Reader & Analyzer",
    page_icon="📚",
    layout="wide"
)

# 初始化 Gemini 客户端
def get_next_api_key():
    """获取下一个API密钥"""
    if "api_key_cycle" not in st.session_state:
        st.session_state.api_key_cycle = cycle(st.secrets["GOOGLE_API_KEYS"])
    return next(st.session_state.api_key_cycle)

def init_gemini_client():
    return genai.Client(
        api_key=get_next_api_key(),
    )

# PDF转图片函数
def convert_pdf_to_images(pdf_document):
    images = []
    for page_num in range(pdf_document.page_count):
        page = pdf_document[page_num]
        pix = page.get_pixmap()
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

# 读取EPUB文件并按章节分割
def read_epub_by_chapters(file_content):
    """读取EPUB文件并按章节分割内容"""
    try:
        # 创建临时文件
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.epub') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # 读取EPUB文件
            book = epub.read_epub(temp_file_path)
            
            # 存储章节内容
            chapters = []
            chapter_titles = []
            
            # 遍历所有项目，提取章节内容
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    # 解析HTML内容
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    
                    # 尝试获取章节标题
                    title = soup.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    chapter_title = title.get_text() if title else f"Chapter {len(chapters) + 1}"
                    
                    # 获取章节文本内容
                    text = soup.get_text()
                    
                    # 如果章节内容不为空，则添加到列表中
                    if text.strip():
                        chapters.append(text)
                        chapter_titles.append(chapter_title)
            
            return chapters, chapter_titles
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file_path)
            except:
                pass
    except Exception as e:
        st.error(f"读取EPUB文件失败: {str(e)}")
        return [], []

# 计算文本字数
def count_words(text):
    """计算文本中的字数（中文字符 + 英文单词）"""
    # 匹配中文字符
    chinese_characters = re.findall(r'[\u4e00-\u9fff]', text)
    # 匹配英文单词
    english_words = re.findall(r'\b[a-zA-Z]+\b', text)
    # 返回中文字符数 + 英文单词数
    return len(chinese_characters) + len(english_words)

# 分析文档页面内容
def analyze_page_content(client, prompt, content, page_info):
    try:
        full_prompt = f"""{content}

{prompt}"""
        
        model = "gemini-2.0-flash-exp"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=full_prompt)],
            ),
        ]

        response = client.models.generate_content(
            model=model,
            contents=contents,
        )
        
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        return f"Analysis error: {str(e)}"

# Main page
st.title("📚 Document Analyzer")

# 初始化session state
if 'current_chapter' not in st.session_state:
    st.session_state.current_chapter = 0
    print(f"初始化 current_chapter: {st.session_state.current_chapter}")
if 'document_type' not in st.session_state:
    st.session_state.document_type = None
if 'epub_chapters' not in st.session_state:
    st.session_state.epub_chapters = []
if 'epub_chapter_titles' not in st.session_state:
    st.session_state.epub_chapter_titles = []

# 文件上传区域
uploaded_file = st.file_uploader("Upload Document (PDF/EPUB)", type=["pdf", "epub"])

# 添加一个标记来跟踪文件是否已经处理过
if 'file_processed' not in st.session_state:
    st.session_state.file_processed = False
    print('file_processed', st.session_state.file_processed)

# 只有当文件上传且未处理过，或者文件发生变化时才处理文件
if uploaded_file is not None:
    # 检查文件是否发生变化
    current_file_name = uploaded_file.name
    print('current_file_name', current_file_name)
    print('====')
    print("'last_file_name' not in st.session_state", 'last_file_name' not in st.session_state)
    if 'last_file_name' not in st.session_state or st.session_state.last_file_name != current_file_name:
        st.session_state.last_file_name = current_file_name
        print('last_file_name', st.session_state.last_file_name)
        st.session_state.file_processed = False
        print('in uploaded_file file_processed', st.session_state.file_processed)
    
    if not st.session_state.file_processed:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        if file_extension == "pdf":
            st.session_state.document_type = "pdf"
            # 重置EPUB相关状态
            st.session_state.epub_chapters = []
            st.session_state.epub_chapter_titles = []
            st.session_state.epub_pages = []
            st.session_state.current_chapter = 0
            st.session_state.current_page = 0
        elif file_extension == "epub":
            st.session_state.document_type = "epub"
            # 读取EPUB文件
            epub_content = uploaded_file.read()
            st.session_state.epub_chapters, st.session_state.epub_chapter_titles = read_epub_by_chapters(epub_content)
            
            # 设置初始章节
            if st.session_state.epub_chapters:
                st.session_state.current_chapter = 0
                print(f"上传EPUB文件后设置 current_chapter: {st.session_state.current_chapter}")
        
        # 标记文件已处理
        st.session_state.file_processed = True
        print('file_processed', st.session_state.file_processed)

# 在侧边栏添加提示词输入和文档预览
with st.sidebar:
    st.subheader("💭 Analysis Prompt")
    user_prompt = st.text_area(
        "Enter analysis prompt",
        height=150,
        placeholder="Example: Summarize the main content of this page..."
    )
    
    # 添加页面批量分析选项
    pages_per_batch = st.number_input(
        "Pages per analysis batch",
        min_value=1,
        max_value=100,
        value=1,
        help="Select how many pages to analyze together. Higher values mean fewer API calls but may affect analysis quality."
    )
    
    # 添加一个美观的Enter按钮
    if st.button("Enter", type="primary", use_container_width=True):
        st.session_state.analyze_trigger = True
    
    # 在侧边栏显示文档预览
    if uploaded_file is not None:
        try:
            if st.session_state.document_type == "pdf":
                # 读取PDF文件
                pdf_bytes = uploaded_file.read()
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
                
                pdf_viewer(pdf_bytes)


            
            elif st.session_state.document_type == "epub" and st.session_state.epub_chapters:
                # 显示EPUB章节导航和字数统计
                st.subheader("📑 Chapters")
                for i, (title, content) in enumerate(zip(st.session_state.epub_chapter_titles, st.session_state.epub_chapters)):
                    word_count = count_words(content)
                    if st.button(f"{title} ({word_count} 字)", key=f"chapter_{i}", use_container_width=True):
                        st.session_state.current_chapter = i
                        print(f"点击章节按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()

        except Exception as e:
            st.error(f'Error displaying document: {str(e)}')

# 主内容区域
if uploaded_file is not None:
    try:
        if st.session_state.document_type == "pdf":
            # 读取PDF文件（如果还没有读取）
            if 'pdf_document' not in locals():
                pdf_bytes = uploaded_file.read()
                pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            # 显示PDF信息
            st.subheader(f"📄 PDF Document - {pdf_document.page_count} pages")
            
            # 获取当前页面的文本内容用于分析
            if user_prompt:
                with st.spinner('Analyzing page content...'):
                    client = init_gemini_client()
                    
                    # Display analysis results below the PDF
                    st.subheader('📝 Analysis Results')
                    
                    # 计算需要处理的批次数
                    total_pages = pdf_document.page_count
                    batch_count = (total_pages + pages_per_batch - 1) // pages_per_batch
                    
                    # 按批次处理页面
                    for batch in range(batch_count):
                        start_page = batch * pages_per_batch
                        end_page = min(start_page + pages_per_batch, total_pages)
                        
                        with st.spinner(f'📚 Analyzing pages {start_page + 1} to {end_page}...'):
                            # 合并这批页面的文本
                            batch_text = ""
                            for page_num in range(start_page, end_page):
                                batch_text += pdf_document[page_num].get_text() + "\n\n"
                            
                            # 分析合并后的内容
                            analysis = analyze_page_content(client, user_prompt, batch_text, f"PDF Pages {start_page + 1}-{end_page}")
                            
                            # 显示分析结果
                            # st.markdown(f"### 📚 Pages {start_page + 1} to {end_page} Analysis")
                            if start_page + 1 == end_page:
                                st.success(f"Page {start_page + 1} Analysis", icon="📚")
                            else:
                                st.success(f"Pages {start_page + 1} to {end_page} Analysis", icon="📚")
                            st.markdown(analysis)
                            st.markdown("---")  # Add separator
        
        elif st.session_state.document_type == "epub" and st.session_state.epub_chapters:
            # 显示EPUB信息
            total_chapters = len(st.session_state.epub_chapters)
            current_chapter = st.session_state.current_chapter
            current_chapter_title = st.session_state.epub_chapter_titles[current_chapter]
            current_content = st.session_state.epub_chapters[current_chapter]
            
            st.subheader(f"📖 {current_chapter_title}")
            st.caption(f"字数：{count_words(current_content)}")
            
            # 如果有提示词且点击了Enter按钮，才显示分析结果
            if user_prompt and st.session_state.get("analyze_trigger", False):
                with st.spinner('Analyzing content...'):
                    client = init_gemini_client()
                    
                    # 显示分析结果
                    st.subheader('📝 Analysis Results')
                    
                    # 分析当前章节内容
                    with st.spinner(f'📚 Analyzing chapter {current_chapter + 1}...'):
                        analysis = analyze_page_content(client, user_prompt, current_content, f"Chapter {current_chapter + 1}: {current_chapter_title}")
                        st.markdown(analysis)
                        st.markdown("---")  # Add separator
                # 重置分析触发器
                st.session_state.analyze_trigger = False
            
            # 显示当前章节内容
            st.subheader("📄 Chapter Content")
            st.markdown(current_content)
            st.markdown("---")
            
            # 章节导航按钮
            col1, col2 = st.columns(2)
            with col1:
                if current_chapter > 0:
                    if st.button("⏮️ Previous Chapter"):
                        st.session_state.current_chapter -= 1
                        print(f"点击上一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
            with col2:
                if current_chapter < total_chapters - 1:
                    if st.button("⏭️ Next Chapter"):
                        st.session_state.current_chapter += 1
                        print(f"点击下一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
    except Exception as e:
        st.error(f'Error processing document: {str(e)}')