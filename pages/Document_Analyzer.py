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

        if len(images) > 3:
            print(f"警告: 尝试同时分析{len(images)}张图片，可能导致超时")

        # 创建客户端
        client = genai.Client(
            api_key=get_next_api_key(),
        )

        # 创建上传文件列表
        uploaded_files = []

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

        # 调用API生成内容
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

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
                "每批分析页数 (强烈建议每批1页)",
                min_value=1,
                max_value=3,  # 限制最大页数
                value=1,
                help="图片模式下强烈建议每批分析1页以提高成功率"
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
        # 非PDF文件的批次大小设置
        pages_per_batch = st.number_input(
            "Pages per analysis batch",
            min_value=1,
            max_value=100,
            value=5,
            help="Select how many pages to analyze together. Higher values mean fewer API calls but may affect analysis quality."
        )

    # 添加一个美观的Enter按钮
    if st.button("🚀 开始分析", type="primary", use_container_width=True):
        if not user_prompt:
            st.error("请先输入分析提示！")
        else:
            if st.session_state.document_type == "pdf" and st.session_state.pdf_bytes:
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

                # 处理每个批次
                for batch_idx in range(total_batches):
                    start_page = batch_idx * pages_per_batch
                    end_page = min((batch_idx + 1) *
                                   pages_per_batch, total_pages)

                    # 更新进度条
                    progress = (batch_idx) / total_batches
                    progress_bar.progress(progress)
                    status_text.info(
                        f"正在处理第 {start_page + 1}-{end_page} 页 (批次 {batch_idx + 1}/{total_batches})")

                    # 根据分析模式选择处理方法
                    if st.session_state.pdf_analysis_mode == "image" and 'pdf_images' in st.session_state:
                        # 图片模式分析
                        with st.spinner(f"🖼️ 正在使用图片模式分析第 {start_page + 1} 到 {end_page} 页..."):
                            st.info("图片分析中，请耐心等待...")

                            # 显示正在分析的图片
                            cols = st.columns(min(3, end_page - start_page))
                            for i, col in enumerate(cols):
                                if start_page + i < len(st.session_state.pdf_images):
                                    with col:
                                        st.image(st.session_state.pdf_images[start_page + i],
                                                 caption=f"Page {start_page + i + 1}",
                                                 use_column_width=True)

                            # 生成图片分析的提示词
                            image_prompt = f"{user_prompt}\n\n请分析这{'些' if end_page-start_page > 1 else ''}PDF页面的内容。"

                            try:
                                # 分析图片内容
                                analysis = analyze_image_content(
                                    st.session_state.pdf_images[start_page:end_page],
                                    image_prompt
                                )

                                # 添加到合并结果
                                batch_result = f"### 📄 第 {start_page + 1}-{end_page} 页分析结果\n\n{analysis}"
                                combined_analysis.append(batch_result)

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

                # 完成所有批次，显示结果
                progress_bar.progress(1.0)
                status_text.success("✅ 分析完成!")

                # 显示所有批次的合并结果
                st.markdown("## 📊 分析结果")
                for result in combined_analysis:
                    st.markdown(result)
                    st.divider()

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
                                         use_column_width=True)
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

        except Exception as e:
            st.error(f'Error displaying document: {str(e)}')

# 主内容区域
if uploaded_file is not None:
    try:
        if st.session_state.document_type == "pdf":
            # 使用已保存的PDF信息，避免重复读取文件
            page_count = st.session_state.pdf_document_info['page_count']
            doc_title = st.session_state.pdf_document_info['title']

            # 显示PDF信息
            st.subheader(f"📄 PDF文档 - {doc_title} ({page_count} 页)")

            # 获取当前页面的文本内容用于分析
            if user_prompt:
                with st.spinner('分析页面内容中...'):
                    client = init_gemini_client()

                    # 显示分析结果
                    st.subheader('📝 分析结果')

                    # 计算需要处理的批次数
                    total_pages = page_count
                    batch_count = (
                        total_pages + pages_per_batch - 1) // pages_per_batch

                    # 分析处理的具体逻辑
                    for batch in range(batch_count):
                        start_page = batch * pages_per_batch
                        end_page = min(
                            start_page + pages_per_batch, total_pages)

                        with st.spinner(f'📚 正在分析第 {start_page + 1} 到 {end_page} 页...'):
                            # 根据分析模式选择不同的处理方式
                            if st.session_state.pdf_analysis_mode == "text":
                                # 文本模式：使用预先存储的PDF字节重新打开文档以提取文本
                                batch_text = ""
                                # 重新打开PDF以获取文本（这样可以确保每次都能正确获取）
                                with fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf") as pdf_doc:
                                    for page_num in range(start_page, end_page):
                                        batch_text += pdf_doc[page_num].get_text() + \
                                            "\n\n"

                                # 分析合并后的文本内容
                                analysis = analyze_page_content(
                                    client, user_prompt, batch_text, f"PDF Pages {start_page + 1}-{end_page}")
                            else:
                                # 图片模式：分析每个页面的图片
                                # 显示正在处理的图片
                                st.subheader(
                                    f"正在分析第 {start_page + 1} 到 {end_page} 页的图片")

                                # 在分析前展示要分析的页面图片
                                img_cols = st.columns(
                                    min(3, end_page - start_page + 1))
                                for i, page_idx in enumerate(range(start_page, end_page)):
                                    if page_idx < len(st.session_state.pdf_images):
                                        with img_cols[i % len(img_cols)]:
                                            st.image(st.session_state.pdf_images[page_idx],
                                                     caption=f"第 {page_idx + 1} 页",
                                                     use_column_width=True)

                                # 创建一个自定义提示词格式
                                image_prompt = f"以下是PDF的第{start_page + 1}页到第{end_page}页的图片。\n\n{user_prompt}"

                                # 允许用户在分析前查看和确认图片
                                st.info("正在使用图片模式分析这些页面。可能需要较长时间，请耐心等待...")

                                # 分析图片内容
                                analysis = analyze_image_content(
                                    st.session_state.pdf_images[start_page:end_page],
                                    image_prompt
                                )

                                # 如果分析失败，可以选择切换到文本模式
                                if "图片分析错误" in analysis or "图片分析超时" in analysis:
                                    st.error("图片分析失败，正在尝试使用文本模式作为备选...")
                                    # 尝试使用文本模式作为备选
                                    try:
                                        with fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf") as pdf_doc:
                                            backup_text = ""
                                            for page_num in range(start_page, end_page):
                                                backup_text += pdf_doc[page_num].get_text(
                                                ) + "\n\n"

                                        backup_analysis = analyze_page_content(
                                            client, user_prompt, backup_text, f"PDF Pages {start_page + 1}-{end_page}")

                                        # 组合结果
                                        analysis += "\n\n---\n\n**文本模式备选分析结果：**\n" + backup_analysis
                                    except Exception as e:
                                        st.error(f"备选文本分析也失败了: {str(e)}")

                            # 显示分析结果
                            if start_page + 1 == end_page:
                                st.success(
                                    f"第 {start_page + 1} 页分析", icon="📚")
                            else:
                                st.success(
                                    f"第 {start_page + 1} 到 {end_page} 页分析", icon="📚")
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
                        analysis = analyze_page_content(
                            client, user_prompt, current_content, f"Chapter {current_chapter + 1}: {current_chapter_title}")
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
                        print(
                            f"点击上一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
            with col2:
                if current_chapter < total_chapters - 1:
                    if st.button("⏭️ Next Chapter"):
                        st.session_state.current_chapter += 1
                        print(
                            f"点击下一章按钮，设置 current_chapter: {st.session_state.current_chapter}")
                        st.rerun()
    except Exception as e:
        st.error(f'Error processing document: {str(e)}')
