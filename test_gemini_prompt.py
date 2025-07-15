import os
import sys
import tempfile
from datetime import datetime
from pages.SEC_Earnings_Analyzer import SixKProcessor, Document, config

def test_6k_processing():
    """测试6-K文件处理功能"""
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    print(f"临时目录: {temp_dir}")
    
    try:
        # 初始化6-K处理器
        processor = SixKProcessor(temp_dir)
        
        # 测试用例：BABA的6-K文件
        ticker = "BABA"
        cik = "1577552"  # BABA的CIK
        
        # 创建一个测试文档 - 使用正确的SEC URL格式（无破折号）
        test_doc = Document(
            type='SEC Filing',
            title=f"{ticker} 6-K - (2024-01-01)",
            date=datetime(2024, 1, 1).date(),
            url="https://www.sec.gov/Archives/edgar/data/1577552/000110465924000001/baba-6k_20240101.htm",
            form_type="6-K"
        )
        
        print(f"开始测试6-K处理: {ticker}")
        print(f"测试文档: {test_doc.title}")
        print(f"测试URL: {test_doc.url}")
        
        # 处理6-K文件
        result_docs = processor.process_6k_filing(ticker, cik, test_doc.url, test_doc)
        
        print(f"处理结果: 生成了 {len(result_docs)} 个文档")
        
        for i, doc in enumerate(result_docs):
            print(f"\n文档 {i+1}:")
            print(f"  标题: {doc.title}")
            print(f"  类型: {doc.form_type}")
            print(f"  内容长度: {len(doc.content) if doc.content else 0} 字符")
            if doc.content:
                print(f"  内容预览: {doc.content[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_url_parsing():
    """测试URL解析功能"""
    import re
    
    test_urls = [
        "https://www.sec.gov/Archives/edgar/data/1577552/000110465924000001/baba-6k_20240101.htm",
        "https://www.sec.gov/Archives/edgar/data/1577552/000157755224000001/baba-6k_20240101.htm",
        "https://www.sec.gov/Archives/edgar/data/1577552/000157755224000056/baba-6k_20240101.htm"
    ]
    
    print("测试URL解析（新的18位数字格式）:")
    for url in test_urls:
        # 新的正则表达式：匹配18位数字
        accession_match = re.search(r'/(\d{18})/', url)
        if accession_match:
            accession_no_no_dashes = accession_match.group(1)
            # 重新构造带破折号的格式
            accession_no = f"{accession_no_no_dashes[:10]}-{accession_no_no_dashes[10:12]}-{accession_no_no_dashes[12:]}"
            print(f"  ✅ URL: {url}")
            print(f"     无破折号: {accession_no_no_dashes}")
            print(f"     带破折号: {accession_no}")
        else:
            print(f"  ❌ URL: {url}")
            print(f"     无法解析accession number")

if __name__ == "__main__":
    print("开始测试6-K文件处理功能...")
    
    # 先测试URL解析
    test_url_parsing()
    
    print("\n" + "="*50)
    
    # 再测试6-K处理
    success = test_6k_processing()
    
    if success:
        print("\n✅ 测试完成")
    else:
        print("\n❌ 测试失败") 