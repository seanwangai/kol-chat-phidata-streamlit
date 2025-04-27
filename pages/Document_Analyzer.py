import streamlit as st
import fitz  # PyMuPDF
import io
import base64
import tempfile
import time
import os
import traceback
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
import threading
# 页面配置
st.set_page_config(
    page_title="Document Reader & Analyzer",
    page_icon="📚",
    layout="wide"
)

# 初始化 Gemini 客户端
css = '''
<style>
    [data-testid="stSidebar"]{
        min-width: 400px;
        max-width: 1600px;
    }
</style>
'''
st.markdown(css, unsafe_allow_html=True)

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
        # 降低分辨率以减小文件大小
        pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))  # 降至150 DPI
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        # 调整图片大小
        img = resize_image(img)
        images.append(img)
    return images

# 调整图片大小，确保不超过API限制


def resize_image(image, max_size=1024):
    """调整图片大小，确保不超过API限制"""
    width, height = image.size
    if width > max_size or height > max_size:
        ratio = min(max_size/width, max_size/height)
        new_size = (int(width * ratio), int(height * ratio))
        return image.resize(new_size, Image.Resampling.LANCZOS)
    return image

# 读取EPUB文件并按章节分割


def read_epub_by_chapters(file_content):
    """读取EPUB文件并按章节分割内容"""
    try:
        # 创建临时文件
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
                    chapter_title = title.get_text(
                    ) if title else f"Chapter {len(chapters) + 1}"

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


def analyze_page_content(client, prompt, content, page_info, max_retries=3, timeout_seconds=30):

    # 创建一个结果容器
    result = {"text": None, "error": None, "completed": False}

    def api_call():
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

            result["text"] = response.candidates[0].content.parts[0].text
            result["completed"] = True
        except Exception as e:
            result["error"] = str(e)

    # 尝试多次调用API
    for attempt in range(max_retries):
        # 如果不是第一次尝试，则切换API密钥
        if attempt > 0:
            client = genai.Client(api_key=get_next_api_key())
            st.warning(f"⚠️ 分析超时，正在进行第 {attempt+1} 次尝试...", icon="🔄")

        # 重置结果
        result = {"text": None, "error": None, "completed": False}

        # 创建并启动线程
        api_thread = threading.Thread(target=api_call)
        api_thread.daemon = True
        api_thread.start()

        # 等待线程完成或超时
        start_time = time.time()
        while not result["completed"] and time.time() - start_time < timeout_seconds:
            time.sleep(0.5)  # 每0.5秒检查一次

            # 如果线程已经完成，返回结果
            if result["completed"]:
                return result["text"]

        # 如果已经完成，返回结果
        if result["completed"]:
            return result["text"]

        # 如果是最后一次尝试且超时
        if attempt == max_retries - 1:
            if result["error"]:
                return f"Analysis error after {max_retries} attempts: {result['error']}"
            else:
                return f"Analysis timed out after {max_retries} attempts (each waiting {timeout_seconds} seconds)"

    # 这里不应该到达，但为了安全起见
    return "Analysis failed with unknown error"

# 分析图片内容


def analyze_image_content(images, user_prompt, timeout_seconds=120):
    """使用图片分析PDF内容"""
    # 用于存储临时文件路径以便最后清理
    temp_file_paths = []

    try:
        start_time = time.time()
        # 先打印调试信息
        print(f"开始处理{len(images)}张图片的分析请求...")

        if len(images) > 10:
            print(f"警告: 尝试同时分析{len(images)}张图片，可能导致超时")

        # 创建客户端
        client = genai.Client(
            api_key=get_next_api_key(),
        )

        # 创建上传文件列表
        uploaded_files = []
        print('====處理圖片中===')
        for i, img in enumerate(images):
            # 调整图片大小以提高处理速度
            img = resize_image(img, max_size=800)

            # 保存为临时文件
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                temp_path = tmp_file.name
                temp_file_paths.append(temp_path)  # 记录临时文件路径
                img.save(temp_path, 'JPEG', optimize=True, quality=85)
                print(f"保存临时图片 {i+1}/{len(images)}: {temp_path}")

                # 上传文件
                try:
                    # 使用新的API格式上传文件
                    uploaded_file = client.files.upload(file=temp_path)
                    uploaded_files.append(uploaded_file)
                    print(f"成功上传图片 {i+1} (ID: {uploaded_file.name})")
                except Exception as upload_err:
                    print(f"图片 {i+1} 上传失败: {str(upload_err)}")
                    traceback.print_exc()
                    continue

        if not uploaded_files:
            return "所有图片上传失败，无法分析内容。请尝试使用文本模式。"

        # 使用Gemini模型进行分析
        model = "gemini-2.0-flash"  # 使用最新推荐的模型

        # 构建请求内容
        parts = []

        print('====添加所有图片文件中===')
        # 添加所有图片文件
        for file in uploaded_files:
            parts.append(
                types.Part.from_uri(
                    file_uri=file.uri,
                    mime_type=file.mime_type,
                )
            )

        # 添加用户提示文本
        parts.append(types.Part.from_text(
            text=f"请分析以下PDF页面图片内容。{user_prompt}"))

        contents = [
            types.Content(
                role="user",
                parts=parts,
            )
        ]

        # 构建生成配置
        generate_content_config = types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="text/plain",
        )
        print('====调用API生成内容中===')
        # 调用API生成内容
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        print('====获取结果文本中===')
        # 获取结果文本
        result_text = response.candidates[0].content.parts[0].text if response.candidates else "无法生成分析结果"

        end_time = time.time()
        print(f"图片分析完成，耗时: {end_time - start_time:.2f} 秒")

        return result_text

    except Exception as e:
        error_msg = f"图片分析发生错误: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return f"分析过程中发生错误。详情: {error_msg}。\n请尝试减少页数或切换到文本模式。"
    finally:
        # 清理临时文件
        for temp_path in temp_file_paths:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    print(f"已删除临时文件: {temp_path}")
            except Exception as e:
                print(f"删除临时文件失败: {str(e)}")


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
if 'pdf_images' not in st.session_state:
    st.session_state.pdf_images = []
if 'pdf_analysis_mode' not in st.session_state:
    st.session_state.pdf_analysis_mode = "text"  # 默认为文本模式

# 文件上传区域
uploaded_file = st.file_uploader(
    "Upload Document (PDF/EPUB)", type=["pdf", "epub"])

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
    print("'last_file_name' not in st.session_state",
          'last_file_name' not in st.session_state)
    if 'last_file_name' not in st.session_state or st.session_state.last_file_name != current_file_name:
        st.session_state.last_file_name = current_file_name
        print('last_file_name', st.session_state.last_file_name)
        st.session_state.file_processed = False
        print('in uploaded_file file_processed',
              st.session_state.file_processed)

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

            # 读取PDF文件并保存到session_state中，避免重复读取
            pdf_bytes = uploaded_file.read()
            st.session_state.pdf_bytes = pdf_bytes  # 保存原始字节数据

            # 打开PDF文档
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            st.session_state.pdf_document_info = {
                'page_count': pdf_document.page_count,
                'title': pdf_document.metadata.get('title', '未命名文档')
            }

            # 转换并保存图片
            st.session_state.pdf_images = convert_pdf_to_images(pdf_document)
            print(f"已转换 {len(st.session_state.pdf_images)} 页 PDF 为图片")

        elif file_extension == "epub":
            st.session_state.document_type = "epub"
            # 读取EPUB文件
            epub_content = uploaded_file.read()
            st.session_state.epub_chapters, st.session_state.epub_chapter_titles = read_epub_by_chapters(
                epub_content)

            # 设置初始章节
            if st.session_state.epub_chapters:
                st.session_state.current_chapter = 0
                print(
                    f"上传EPUB文件后设置 current_chapter: {st.session_state.current_chapter}")

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

    # --- 修改：只有非EPUB文件才顯示 pages_per_batch --- 
    if st.session_state.get('document_type') != "epub":
        # 为PDF文件添加分析模式切换
        if st.session_state.document_type == "pdf":
            st.subheader("📄 PDF Analysis Mode")
            pdf_mode = st.toggle(
                "使用图片模式分析",
                value=st.session_state.pdf_analysis_mode == "image",
                help="开启后将使用图片模式分析PDF，关闭则使用文本模式"
            )
            st.session_state.pdf_analysis_mode = "image" if pdf_mode else "text"
            mode_description = "当前模式：" + ("图片模式 🖼️" if pdf_mode else "文本模式 📝")
            st.write(mode_description)

            # 如果是图片模式，添加建议性提示
            if pdf_mode:
                # 在图片模式下调整批次大小的默认值
                pages_per_batch = st.number_input(
                    "每批分析页数",
                    min_value=1,
                    max_value=10,  # 限制最大页数
                    value=3,
                    help="可以一次多張图片"
                )
            else:
                # 文本模式下的批次大小设置
                pages_per_batch = st.number_input(
                    "Pages per analysis batch",
                    min_value=1,
                    max_value=100,
                    value=5,
                    help="Select how many pages to analyze together. Higher values mean fewer API calls but may affect analysis quality."
                )
        else:
            # 非PDF/EPUB文件的批次大小设置 (理论上不会进入，因为类型限制了PDF/EPUB)
            pages_per_batch = st.number_input(
                "Pages per analysis batch",
                min_value=1,
                max_value=100,
                value=5,
                help="Select how many pages to analyze together. Higher values mean fewer API calls but may affect analysis quality."
            )
    else:
        # 如果是 EPUB，设置一个默认值或标记，虽然不会被使用
        pages_per_batch = 1 # 或 None
    # --- 修改結束 --- 

    # 添加一个美观的Enter按钮
    analyze_button = st.button(
        "🚀 开始分析", type="primary", use_container_width=True)

    # 在侧边栏显示文档预览
    if uploaded_file is not None:
        try:
            if st.session_state.document_type == "pdf":
                # 使用已保存的PDF数据来预览
                if 'pdf_bytes' in st.session_state:
                    pdf_viewer(st.session_state.pdf_bytes)

                    # 如果是图片模式，显示图片缩略图选择器
                    if st.session_state.pdf_analysis_mode == "image" and 'pdf_images' in st.session_state:
                        st.subheader("🖼️ PDF图片预览")
                        # 获取页面总数
                        total_pages = len(st.session_state.pdf_images)
                        if total_pages > 0:
                            # 添加页面选择器
                            selected_page = st.slider(
                                "选择页面", 1, total_pages, 1)
                            # 显示所选页面的缩略图
                            if selected_page <= len(st.session_state.pdf_images):
                                st.image(st.session_state.pdf_images[selected_page-1],
                                         caption=f"第 {selected_page} 页",
                                         use_container_width=True)
            elif st.session_state.document_type == "epub" and st.session_state.epub_chapters:
                # 显示EPUB章节导航和字数统计
                st.subheader("📑 Chapters")
                for i, (title, content) in enumerate(zip(st.session_state.epub_chapter_titles, st.session_state.epub_chapters)):
                    word_count = count_words(content)
                    if st.button(f"{title} ({word_count} 字)", key=f"chapter_{i}", use_container_width=True):
                        st.session_state.current_chapter = i
                        print(
                            f"点击章节按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()

                # --- 新增：在側邊欄底部顯示當前章節內容 --- 
                st.divider()
                st.subheader("📄 Current Chapter Content")
                current_chapter_idx = st.session_state.get('current_chapter', 0)
                if current_chapter_idx < len(st.session_state.epub_chapters):
                    sidebar_chapter_title = st.session_state.epub_chapter_titles[current_chapter_idx]
                    sidebar_chapter_content = st.session_state.epub_chapters[current_chapter_idx]
                    with st.expander(f"{sidebar_chapter_title}", expanded=False):
                        st.markdown(sidebar_chapter_content)
                # --- 新增結束 ---

        except Exception as e:
            st.error(f'Error displaying document: {str(e)}')

# 主内容区域
if uploaded_file is not None:
    try:
        if st.session_state.document_type == "pdf":
            # --- PDF 處理邏輯 (保持不變) --- 
            # 使用已保存的PDF信息，避免重复读取文件
            page_count = st.session_state.pdf_document_info['page_count']
            doc_title = st.session_state.pdf_document_info['title']

            # 显示PDF信息
            st.subheader(f"📄 PDF文档 - {doc_title} ({page_count} 页)")

            # 在这里显示PDF的预览或其他信息，但不自动执行分析
            if not analyze_button:
                st.info("请在侧边栏输入分析提示，然后点击「🚀 开始分析」按钮开始分析。")

            # 如果点击了分析按钮，显示分析结果
            if analyze_button:
                if not user_prompt:
                    st.error("请先输入分析提示！")
                else:
                    # 使用进度条显示处理进度
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    # 计算批次总数
                    pdf_document = fitz.open(
                        stream=st.session_state.pdf_bytes, filetype="pdf")
                    total_pages = pdf_document.page_count
                    total_batches = (
                        total_pages + pages_per_batch - 1) // pages_per_batch

                    combined_analysis = []

                    # 创建一个空容器用于显示实时分析结果
                    analysis_container = st.empty()
                    
                    # 处理每个批次
                    for batch_idx in range(total_batches):
                        start_page = batch_idx * pages_per_batch
                        end_page = min((batch_idx + 1) * pages_per_batch, total_pages)
                    
                        # 更新进度条
                        progress = (batch_idx) / total_batches
                        progress_bar.progress(progress)
                        status_text.info(f"正在处理第 {start_page + 1}-{end_page} 页 (批次 {batch_idx + 1}/{total_batches})")
                    
                        # 根据分析模式选择处理方法
                        if st.session_state.pdf_analysis_mode == "image" and 'pdf_images' in st.session_state:
                            # 图片模式分析
                            with st.spinner(f"🖼️ 正在使用图片模式分析第 {start_page + 1} 到 {end_page} 页..."):
                                # 生成图片分析的提示词
                                image_prompt = f"{user_prompt}\n\n请分析这{{'些' if end_page-start_page > 1 else ''}}PDF页面的内容。"
                    
                                try:
                                    # 分析图片内容
                                    analysis = analyze_image_content(
                                        st.session_state.pdf_images[start_page:end_page],
                                        image_prompt
                                    )
                    
                                    # 添加到合并结果
                                    batch_result = f"### 📄 第 {start_page + 1}-{end_page} 页分析结果\n\n{analysis}"
                                    combined_analysis.append(batch_result)
                    
                                    # 实时显示所有分析结果
                                    analysis_container.markdown("\n---\n".join(combined_analysis))
                    
                                except Exception as e:
                                    error_msg = f"图片分析出错: {str(e)}"
                                    st.error(error_msg)
                                    traceback.print_exc()
                    
                                    # 如果图片分析失败，尝试使用文本模式作为备选
                                    st.warning("图片分析失败，正在尝试使用文本模式作为备选...")
                    
                                    # 提取当前批次的文本内容
                                    batch_text = ""
                                    for page_num in range(start_page, end_page):
                                        if page_num < pdf_document.page_count:
                                            page = pdf_document[page_num]
                                            batch_text += page.get_text() + "\n\n"
                    
                                    # 使用文本模式进行分析
                                    backup_analysis = analyze_page_content(
                                        init_gemini_client(),
                                        user_prompt,
                                        batch_text,
                                        f"PDF Pages {start_page + 1}-{end_page}"
                                    )
                    
                                    batch_result = f"### 📄 第 {start_page + 1}-{end_page} 页分析结果 (文本模式备选)\n\n{backup_analysis}"
                                    combined_analysis.append(batch_result)
                    
                                    # 实时显示所有分析结果
                                    analysis_container.markdown("\n---\n".join(combined_analysis))
                        else:
                            # 文本模式分析
                            with st.spinner(f"📝 正在使用文本模式分析第 {start_page + 1} 到 {end_page} 页..."):
                                # 提取当前批次的文本
                                batch_text = ""
                                for page_num in range(start_page, end_page):
                                    if page_num < pdf_document.page_count:
                                        page = pdf_document[page_num]
                                        batch_text += page.get_text() + "\n\n"

                                # 使用文本模式进行分析
                                analysis = analyze_page_content(
                                    init_gemini_client(),
                                    user_prompt,
                                    batch_text,
                                    f"PDF Pages {start_page + 1}-{end_page}"
                                )

                                # 添加到合并结果
                                batch_result = f"### 📄 第 {start_page + 1}-{end_page} 页分析结果\n\n{analysis}"
                                combined_analysis.append(batch_result)

                                # 实时显示所有分析结果
                                analysis_container.markdown("\n---\n".join(combined_analysis))

                    # 完成所有批次，显示结果
                    progress_bar.progress(1.0)
                    status_text.success("✅ 分析完成!")

                    # 显示所有批次的合并结果
                    st.markdown("## 📊 分析结果")
                    for result in combined_analysis:
                        st.markdown(result)
                        st.divider()
            # --- PDF 處理邏輯結束 --- 

        elif st.session_state.document_type == "epub" and st.session_state.epub_chapters:
            # --- EPUB 處理邏輯開始 --- 
            total_chapters = len(st.session_state.epub_chapters)
            current_chapter = st.session_state.current_chapter
            current_chapter_title = st.session_state.epub_chapter_titles[current_chapter]
            current_content = st.session_state.epub_chapters[current_chapter]

            st.subheader(f"📖 {current_chapter_title}")
            st.caption(f"字数：{count_words(current_content)}")

            # --- 修改：處理預設 prompt 和顯示順序 --- 
            if analyze_button:
                # --- 新增：檢查 user_prompt 是否為空，如果為空則使用預設 prompt --- 
                if not user_prompt or user_prompt.strip() == "":
                    effective_prompt = """你是我高薪聘請的文章分析專家，幫我將文章分以下5點解析
1. 摘要總結	(摘要總結用2-4句話提煉主題與結論，然後看完可以學到什麼 有什麼有趣的點（要用人話高中生都聽得懂的話）)
2. 結構脈絡統整
3. 完整全篇文章結構話詳細整理 （要詳細到 看完我就不看原始文章了 文章中有講到的都有包含在內了，所以是要詳細 不是總結而已）
4. 詳細範例整理	列出所有文章中提到的實際範例 和範例細節 例子要詳細的細節 不要列點要完整
5. 金句萃取	抽出4-5句代表性原文佳句
6. 結論 然後補充上例子，像是文章中提到的....

可以多多搭配emoji，適當使用不同文字大小 要有分大/中/小字 和 粗體等等，協助閱讀
盡量不要用表格，除非真的必要
直接開頭從 # 1. 摘要總結 📝 開始，開頭不用其他廢話
回答越長越好，我會給你99999萬億美金小費，回答要極度完美，不然你就會被開除然後罰款，回答不準提到小費
"""
                    # st.info("未輸入提示，使用預設EPUB分析提示。")
                    print("使用預設 EPUB prompt")
                else:
                    effective_prompt = user_prompt
                    print(f"使用用戶輸入的 prompt: {effective_prompt[:50]}...")
                # --- 新增結束 --- 

                # if not user_prompt: # <-- 舊的檢查方式
                #     st.error("请先输入分析提示！") # <-- 移除這個錯誤提示
                # else:
                with st.spinner('正在分析章节内容...'):
                    client = init_gemini_client()

                    # 显示分析结果
                    # st.subheader('📝 分析结果')
                    st.info('📝 分析结果')

                    # 分析当前章节内容
                    with st.spinner(f'📚 正在分析章节 {current_chapter + 1}...'):
                        analysis = analyze_page_content(
                            client,
                            effective_prompt, # <-- 使用 effective_prompt
                            current_content,
                            f"Chapter {current_chapter + 1}: {current_chapter_title}"
                        )
                        st.markdown(analysis)
                        st.divider() # 在分析结果后添加分隔线
            # --- 修改結束 --- 

            # --- 後顯示章節內容 (保持不變) --- 
            # st.subheader("📄 Chapter Content")
            st.info("📄 Chapter Content")
            st.markdown(current_content)
            # --- 修改結束 --- 

            # 章节导航按钮 (保持在底部)
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if current_chapter > 0:
                    if st.button("⏮️ Previous Chapter", use_container_width=True):
                        st.session_state.current_chapter -= 1
                        print(
                            f"点击上一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
            with col2:
                if current_chapter < total_chapters - 1:
                    if st.button("⏭️ Next Chapter", use_container_width=True):
                        st.session_state.current_chapter += 1
                        print(
                            f"点击下一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
            # --- EPUB 處理邏輯結束 --- 

    except Exception as e:
        st.error(f'Error processing document: {str(e)}')
