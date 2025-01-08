from pathlib import Path
import fitz  # PyMuPDF for PDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import streamlit as st
from docx import Document  # 添加 python-docx 支持


def read_pdf(file_path: Path) -> str:
    """读取PDF文件内容"""
    try:
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        st.error(f"读取PDF文件失败 {file_path}: {str(e)}")
        return ""


def read_epub(file_path: Path) -> str:
    """读取EPUB文件内容"""
    try:
        book = epub.read_epub(str(file_path))
        texts = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                texts.append(soup.get_text())
        return "\n".join(texts)
    except Exception as e:
        st.error(f"读取EPUB文件失败 {file_path}: {str(e)}")
        return ""


def read_txt(file_path: Path) -> str:
    """读取TXT文件内容"""
    try:
        return file_path.read_text(encoding='utf-8')
    except Exception as e:
        st.error(f"读取TXT文件失败 {file_path}: {str(e)}")
        return ""


def read_docx(file_path: Path) -> str:
    """读取DOCX文件内容"""
    try:
        doc = Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return "\n".join(text)
    except Exception as e:
        st.error(f"读取DOCX文件失败 {file_path}: {str(e)}")
        return ""


def get_expert_content(expert_folder: Path) -> str:
    """读取专家文件夹中的所有文件内容"""
    content = ""

    # 首先读取TXT文件
    txt_files = list(expert_folder.glob('*.txt'))
    for txt_file in txt_files:
        content += read_txt(txt_file) + "\n\n"

    # 读取DOCX文件
    docx_files = list(expert_folder.glob('*.docx'))
    for docx_file in docx_files:
        content += read_docx(docx_file) + "\n\n"

    # 读取PDF文件
    pdf_files = list(expert_folder.glob('*.pdf'))
    for pdf_file in pdf_files:
        content += read_pdf(pdf_file) + "\n\n"

    # 读取EPUB文件
    epub_files = list(expert_folder.glob('*.epub'))
    for epub_file in epub_files:
        content += read_epub(epub_file) + "\n\n"

    return content.strip()
