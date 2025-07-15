#!/usr/bin/env python3
"""
测试数据分析师页面的核心功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入数据获取功能
from pages.SEC_Earnings_Analyzer import get_sec_filings, get_available_quarters, get_cik_map

def test_cik_mapping():
    """测试CIK映射功能"""
    print("="*50)
    print("测试 CIK 映射功能")
    print("="*50)
    
    try:
        cik_map = get_cik_map()
        print(f"成功获取 CIK 映射，共 {len(cik_map)} 个公司")
        
        # 测试几个知名公司
        test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'META']
        for ticker in test_tickers:
            cik = cik_map.get(ticker)
            print(f"  {ticker}: {cik}")
        
        return True
    except Exception as e:
        print(f"CIK映射测试失败: {e}")
        return False

def test_sec_filings():
    """测试SEC文件获取功能"""
    print("\n" + "="*50)
    print("测试 SEC 文件获取功能")
    print("="*50)
    
    try:
        ticker = "AAPL"
        print(f"正在获取 {ticker} 的 SEC 文件...")
        
        filings = get_sec_filings(ticker, years=1)  # 只获取1年的数据用于测试
        
        if filings:
            print(f"成功获取 {len(filings)} 个 SEC 文件:")
            for i, filing in enumerate(filings[:5]):  # 只显示前5个
                print(f"  {i+1}. {filing['title']} ({filing['date']})")
        else:
            print("未获取到 SEC 文件")
        
        return len(filings) > 0
    except Exception as e:
        print(f"SEC文件测试失败: {e}")
        return False

def test_earnings_quarters():
    """测试财报会议记录获取功能"""
    print("\n" + "="*50)
    print("测试财报会议记录获取功能")
    print("="*50)
    
    try:
        ticker = "AAPL"
        print(f"正在获取 {ticker} 的财报会议记录...")
        
        quarters = get_available_quarters(ticker)
        
        if quarters:
            print(f"成功获取 {len(quarters)} 个财报会议记录:")
            for i, quarter in enumerate(quarters[:5]):  # 只显示前5个
                print(f"  {i+1}. {quarter['title']} ({quarter['date']})")
        else:
            print("未获取到财报会议记录")
        
        return len(quarters) > 0
    except Exception as e:
        print(f"财报会议记录测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始测试数据分析师页面核心功能...")
    
    results = []
    
    # 测试CIK映射
    results.append(test_cik_mapping())
    
    # 测试SEC文件获取
    results.append(test_sec_filings())
    
    # 测试财报会议记录获取
    results.append(test_earnings_quarters())
    
    # 总结测试结果
    print("\n" + "="*50)
    print("测试结果总结")
    print("="*50)
    
    test_names = ["CIK映射", "SEC文件获取", "财报会议记录获取"]
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("🎉 所有测试都通过！数据分析师页面的核心功能正常工作。")
        return True
    else:
        print("⚠️  部分测试失败，请检查网络连接或相关配置。")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 