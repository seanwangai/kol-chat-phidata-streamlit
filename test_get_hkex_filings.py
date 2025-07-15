import os
import re
import httpx
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin

class HKStockFilingsDownloader:
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
        """
        根据股票代码获取股票ID
        例如：输入 "1024.HK" 或 "1024" 获取股票ID
        """
        # 清理股票代码，移除.HK后缀
        clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
        
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
                print(f"原始响应: {content}")
                
                # 移除JSONP包装 - 尝试不同的结尾格式
                data = None
                if content.startswith('callback(') and content.endswith(');'):
                    json_str = content[9:-2]  # 移除 'callback(' 和 ');'
                    print(f"提取的JSON (标准格式): {json_str}")
                    data = json.loads(json_str)
                elif content.startswith('callback(') and content.endswith('});'):
                    json_str = content[9:-3]  # 移除 'callback(' 和 '});'
                    print(f"提取的JSON (长格式): {json_str}")
                    data = json.loads(json_str)
                else:
                    # 尝试用正则表达式提取JSON部分
                    import re
                    match = re.search(r'callback\((.*)\);?\s*$', content)
                    if match:
                        json_str = match.group(1)
                        print(f"正则提取的JSON: {json_str}")
                        data = json.loads(json_str)
                    else:
                        print(f"无法解析JSONP格式: {content}")
                        return None, None, None
                
                if 'stockInfo' in data and data['stockInfo']:
                    stock_info = data['stockInfo'][0]
                    stock_id = stock_info['stockId']
                    stock_code = stock_info['code']
                    stock_name = stock_info['name']
                    
                    print(f"找到股票: {stock_code} - {stock_name} (ID: {stock_id})")
                    return stock_id, stock_code, stock_name
                else:
                    print(f"未找到股票代码 {ticker} 的信息")
                    return None, None, None
                    
        except Exception as e:
            print(f"获取股票ID时出错: {str(e)}")
            return None, None, None
    
    def get_filings_list(self, stock_id, from_date=None, to_date=None):
        """
        获取指定股票的所有公告列表
        """
        if not from_date:
            from_date = "19990401"  # 默认从1999年开始
        if not to_date:
            to_date = datetime.now().strftime("%Y%m%d")
        
        # 构建POST数据
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
                
                return self.parse_filings_html(response.text)
                
        except Exception as e:
            print(f"获取公告列表时出错: {str(e)}")
            return []
    
    def parse_filings_html(self, html_content):
        """
        解析HTML响应，提取公告链接
        """
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
    
    def categorize_filings(self, filings):
        """
        将公告分为两组：季报年报组和其他组
        """
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
    
    def download_filing(self, filing_info, save_dir):
        """
        下载单个公告文件
        """
        try:
            # 创建保存目录
            os.makedirs(save_dir, exist_ok=True)
            
            # 构建文件名
            release_time = filing_info['release_time'].replace('/', '-').replace(' ', '_').replace(':', '-')
            stock_code = filing_info['stock_code']
            doc_type = filing_info['doc_type'].replace('/', '_').replace(' ', '_')
            
            # 从URL获取原始文件名
            original_filename = filing_info['href'].split('/')[-1]
            filename = f"{release_time}_{stock_code}_{doc_type}_{original_filename}"
            
            # 清理文件名中的特殊字符
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            filepath = os.path.join(save_dir, filename)
            
            # 下载文件
            with httpx.Client(headers=self.headers, timeout=60) as client:
                response = client.get(filing_info['url'])
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                print(f"已下载: {filename}")
                return filepath
                
        except Exception as e:
            print(f"下载文件时出错 {filing_info['url']}: {str(e)}")
            return None
    
    def run(self, ticker, save_dir=None, download_files=True, category='all'):
        """
        主运行函数
        category: 'all' - 所有公告, 'quarterly_annual' - 只处理季报年报, 'others' - 只处理其他公告
        """
        print(f"开始处理股票: {ticker}")
        
        # 获取股票ID
        stock_id, stock_code, stock_name = self.get_stock_id(ticker)
        if not stock_id:
            print(f"无法获取股票 {ticker} 的ID")
            return
        
        # 获取公告列表
        print(f"获取 {stock_code} ({stock_name}) 的公告列表...")
        filings = self.get_filings_list(stock_id)
        
        if not filings:
            print("未找到任何公告")
            return
        
        print(f"共找到 {len(filings)} 个公告")
        
        # 分类公告
        quarterly_annual_filings, other_filings = self.categorize_filings(filings)
        print(f"季报年报组: {len(quarterly_annual_filings)} 个")
        print(f"其他公告组: {len(other_filings)} 个")
        
        # 根据category参数选择要处理的公告
        if category == 'quarterly_annual':
            filings_to_process = quarterly_annual_filings
            print(f"\n处理季报年报组 ({len(filings_to_process)} 个公告):")
        elif category == 'others':
            filings_to_process = other_filings
            print(f"\n处理其他公告组 ({len(filings_to_process)} 个公告):")
        else:  # category == 'all'
            filings_to_process = filings
            print(f"\n处理所有公告 ({len(filings_to_process)} 个公告):")
        
        # 显示公告列表
        print("\n=== 季报年报组 ===")
        for i, filing in enumerate(quarterly_annual_filings, 1):
            print(f"{i}. [{filing['release_time']}] {filing['doc_type']} - {filing['doc_title']} ({filing['file_size']})")
            print(f"   URL: {filing['url']}")
        
        print(f"\n=== 其他公告组 (显示前10个) ===")
        for i, filing in enumerate(other_filings[:10], 1):
            print(f"{i}. [{filing['release_time']}] {filing['doc_type']} - {filing['doc_title']} ({filing['file_size']})")
            print(f"   URL: {filing['url']}")
        
        if len(other_filings) > 10:
            print(f"... 还有 {len(other_filings) - 10} 个其他公告")
        
        # 下载文件
        if download_files and filings_to_process:
            if not save_dir:
                save_dir = f"HK_{stock_code}_{stock_name}"
            
            # 根据类别创建子目录
            if category == 'quarterly_annual':
                save_dir = os.path.join(save_dir, "quarterly_annual")
            elif category == 'others':
                save_dir = os.path.join(save_dir, "others")
            else:  # all
                # 分别创建子目录
                qa_dir = os.path.join(save_dir, "quarterly_annual")
                others_dir = os.path.join(save_dir, "others")
                
                print(f"\n开始下载季报年报到目录: {qa_dir}")
                qa_downloaded = 0
                for filing in quarterly_annual_filings:
                    filepath = self.download_filing(filing, qa_dir)
                    if filepath:
                        qa_downloaded += 1
                    time.sleep(1)
                
                print(f"\n开始下载其他公告到目录: {others_dir}")
                others_downloaded = 0
                for filing in other_filings:
                    filepath = self.download_filing(filing, others_dir)
                    if filepath:
                        others_downloaded += 1
                    time.sleep(1)
                
                print(f"\n下载完成！")
                print(f"季报年报: {qa_downloaded} 个文件")
                print(f"其他公告: {others_downloaded} 个文件")
                return {'quarterly_annual': quarterly_annual_filings, 'others': other_filings}
            
            print(f"\n开始下载到目录: {save_dir}")
            downloaded_count = 0
            
            for filing in filings_to_process:
                filepath = self.download_filing(filing, save_dir)
                if filepath:
                    downloaded_count += 1
                time.sleep(1)  # 避免请求过于频繁
            
            print(f"\n下载完成！共下载 {downloaded_count} 个文件")
        
        return {'quarterly_annual': quarterly_annual_filings, 'others': other_filings}

def main():
    # 创建下载器实例
    downloader = HKStockFilingsDownloader()
    
    # 测试股票代码
    ticker = "1024.HK"
    
    # 运行下载 - 处理所有公告并分类
    result = downloader.run(
        ticker=ticker,
        save_dir=None,  # 使用默认目录名
        download_files=True,  # 是否下载文件
        category='all'  # 'all' - 所有公告, 'quarterly_annual' - 只处理季报年报, 'others' - 只处理其他公告
    )
    
    if result:
        qa_count = len(result['quarterly_annual'])
        others_count = len(result['others'])
        print(f"\n处理完成！")
        print(f"季报年报: {qa_count} 个")
        print(f"其他公告: {others_count} 个")
        print(f"总计: {qa_count + others_count} 个公告")
    else:
        print("未找到任何公告")

if __name__ == "__main__":
    main() 