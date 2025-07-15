#!/usr/bin/env python3
"""测试港股日期解析修复"""

import sys
import os
sys.path.append('.')

from datetime import datetime
from app import HKStockService

class MockCacheManager:
    def __init__(self):
        self.cache = {}
    
    def get_cache_key(self, *args):
        return "|".join(str(arg) for arg in args)
    
    def get(self, key, default=None):
        return None  # 始终返回None，强制重新获取
    
    def set(self, key, value):
        self.cache[key] = value

def test_hk_date_parsing():
    """测试港股日期解析"""
    hk_service = HKStockService(MockCacheManager())
    
    # 测试不同格式的日期
    test_dates = [
        "04/07/2025 19:24",
        "Release Time:04/07/2025 19:24",
        "25/03/2025 16:30",
        "Release Time:25/03/2025 16:30"
    ]
    
    print("测试港股日期解析:")
    for date_str in test_dates:
        parsed_date = hk_service.parse_hk_date(date_str)
        print(f"  {date_str} -> {parsed_date}")

def test_hk_filings_retrieval():
    """测试港股文件获取"""
    print("\n测试港股文件获取:")
    
    # 直接测试HKStockFilingsDownloader
    from app import HKStockFilingsDownloader
    
    downloader = HKStockFilingsDownloader()
    stock_id, stock_code, stock_name = downloader.get_stock_id('1024')
    print(f"Stock ID: {stock_id}, Code: {stock_code}, Name: {stock_name}")
    
    if stock_id:
        # 获取少量数据进行测试
        from_date = "20240101"
        to_date = "20250715"
        cutoff_date = "20240601"  # 设置一个截止日期
        
        def status_callback(msg):
            print(f"  Status: {msg}")
        
        filings = downloader.get_filings_list(stock_id, from_date, to_date, cutoff_date, status_callback)
        print(f"  Total filings: {len(filings)}")
        
        # 分类文件
        quarterly_annual, others = downloader.categorize_filings(filings)
        print(f"  Quarterly/Annual: {len(quarterly_annual)}")
        print(f"  Others: {len(others)}")
        
        # 显示前几个季报年报
        print("\n  前5个季报年报:")
        for i, filing in enumerate(quarterly_annual[:5]):
            print(f"    {i+1}. {filing['release_time']} - {filing['doc_type']}")

if __name__ == "__main__":
    test_hk_date_parsing()
    test_hk_filings_retrieval() 