import os
import sys
import tempfile
import json
from datetime import datetime
from pages.SEC_Earnings_Analyzer import SixKProcessor, Document, config

def test_6k_download_optimization():
    """测试6-K下载优化功能"""
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    print(f"临时目录: {temp_dir}")
    
    try:
        # 初始化6-K处理器
        processor = SixKProcessor(temp_dir)
        
        # 测试用例：BABA的真实6-K文件
        ticker = "BABA"
        cik = "1577552"  # BABA的CIK
        
        # 使用一个真实的6-K文件URL进行测试
        test_doc = Document(
            type='SEC Filing',
            title=f"{ticker} 6-K - (2025-07-14)",
            date=datetime(2025, 7, 14).date(),
            url="https://www.sec.gov/Archives/edgar/data/1577552/000110465925052631/tm2516149d1_6k.htm",
            form_type="6-K"
        )
        
        print(f"开始测试6-K优化下载: {ticker}")
        print(f"测试文档: {test_doc.title}")
        print(f"测试URL: {test_doc.url}")
        
        # 处理6-K文件
        result_docs = processor.process_6k_filing(ticker, cik, test_doc.url, test_doc)
        
        print(f"\n处理结果: 生成了 {len(result_docs)} 个文档")
        
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

def test_file_filtering():
    """测试文件类型筛选逻辑"""
    
    print("\n测试文件类型筛选逻辑:")
    
    # 模拟文件列表
    mock_files = [
        {"name": "tm2516149d1_6k.htm", "size": 50000, "type": "text/html"},
        {"name": "tm2516149d1_ex99-1.htm", "size": 30000, "type": "text/html"},
        {"name": "tm2516149d1_ex99-1.pdf", "size": 200000, "type": "application/pdf"},
        {"name": "tm2516149d1_ex99-1img001.jpg", "size": 100000, "type": "image/jpeg"},
        {"name": "index.html", "size": 5000, "type": "text/html"},
        {"name": "report.xml", "size": 15000, "type": "text/xml"},
        {"name": "data.json", "size": 8000, "type": "application/json"},
    ]
    
    # 筛选逻辑
    target_files = []
    for item in mock_files:
        file_name = item.get('name', '')
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext in ['.pdf', '.htm', '.html']:
            target_files.append(item)
            print(f"  ✅ 保留: {file_name} ({ext})")
        else:
            print(f"  ❌ 跳过: {file_name} ({ext})")
    
    print(f"\n筛选结果: {len(target_files)}/{len(mock_files)} 个文件被保留")
    
    # 进一步筛选ex99文件
    ex99_files = []
    for item in target_files:
        file_name = item.get('name', '').lower()
        if '_ex99' in file_name:
            ex99_files.append(item)
            print(f"  🎯 Ex99文件: {item['name']}")
    
    print(f"Ex99文件: {len(ex99_files)} 个")

if __name__ == "__main__":
    print("开始测试6-K优化功能...")
    
    # 测试文件筛选逻辑
    test_file_filtering()
    
    print("\n" + "="*50)
    
    # 测试实际6-K处理
    success = test_6k_download_optimization()
    
    if success:
        print("\n✅ 测试完成")
    else:
        print("\n❌ 测试失败") 