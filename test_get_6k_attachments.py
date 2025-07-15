import os
import json
import re
from datetime import datetime
from sec_edgar_api import EdgarClient
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import httpx
import warnings
from urllib.parse import urljoin

# URL for the SEC's ticker to CIK mapping file
CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

def get_cik_map():
    """
    Downloads the ticker-to-CIK mapping from the SEC and returns it as a dictionary.
    """
    headers = {'User-Agent': 'Your Name <adsddtion@gmail.com>'}
    response = httpx.get(CIK_MAP_URL, headers=headers)
    response.raise_for_status()
    all_companies = response.json()
    return {company['ticker']: company['cik_str'] for company in all_companies.values()}

def get_6k_filings_with_attachments(ticker: str):
    """
    Fetches all 6-K filings for a given ticker and downloads their attachments.

    Args:
        ticker (str): The stock ticker symbol.
    """
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    edgar = EdgarClient(user_agent="Your Name <adsddtion@gmail.com>")
    
    # Create a directory to save the filings
    base_dir = f"{ticker}_6K_attachments"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        print(f"创建目录: {base_dir}")

    print(f"获取 {ticker} 的所有6-K文件及其附件...")

    try:
        print("获取CIK...")
        ticker_map = get_cik_map()
        cik = ticker_map.get(ticker.upper())

        if not cik:
            print(f"未找到股票代码 {ticker}。")
            return

        print(f"找到CIK: {cik}")
        
        # Get all submissions for the CIK
        submissions = edgar.get_submissions(cik=str(cik).zfill(10))
        
        # The API returns data in a columnar format. We need to transpose it.
        recent = submissions.get('filings', {}).get('recent', {})
        
        # Check if there's any data
        if not recent or 'form' not in recent:
            print(f"未找到 {ticker} 的近期文件。")
            return

        # Create a list of filing dictionaries by transposing the columnar data
        all_6k_filings = []
        forms = recent.get('form', [])
        accession_numbers = recent.get('accessionNumber', [])
        filing_dates = recent.get('filingDate', [])
        primary_documents = recent.get('primaryDocument', [])
        
        for i in range(len(forms)):
            form_type = forms[i]
            if form_type == '6-K':
                all_6k_filings.append({
                    'form': form_type,
                    'accessionNumber': accession_numbers[i],
                    'filingDate': filing_dates[i],
                    'primaryDocument': primary_documents[i],
                })

        if not all_6k_filings:
            print(f"未找到 {ticker} 的6-K文件。")
            return

        print(f"找到 {len(all_6k_filings)} 个6-K文件。开始下载文件及附件...")

        for idx, filing in enumerate(all_6k_filings):
            accession_no = filing['accessionNumber']
            filing_date = filing['filingDate']
            primary_doc = filing['primaryDocument']
            
            print(f"\n处理第 {idx + 1} 个文件: {filing_date} - {accession_no}")
            
            # Create a subdirectory for this filing
            filing_dir = os.path.join(base_dir, f"{filing_date}_{accession_no}")
            if not os.path.exists(filing_dir):
                os.makedirs(filing_dir)
            
            # Download the filing and its attachments
            download_6k_with_attachments(ticker, cik, filing, filing_dir)

    except Exception as e:
        print(f"发生错误: {e}")

def download_6k_with_attachments(ticker: str, cik: str, filing: dict, filing_dir: str):
    """
    Download a 6-K filing and all its attachments.
    """
    accession_no = filing['accessionNumber']
    accession_no_no_dashes = accession_no.replace('-', '')
    primary_doc = filing['primaryDocument']
    
    # Base URL for the filing
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_no_dashes}/"
    
    # Get the filing index to find all documents
    index_url = base_url + "index.json"
    
    headers = {"User-Agent": "Your Name <your_email@example.com>"}
    
    try:
        # Get the index file
        response = httpx.get(index_url, headers=headers)
        response.raise_for_status()
        
        index_data = response.json()
        
        # Get the directory listing
        directory = index_data.get('directory', {})
        items = directory.get('item', [])
        
        if not items:
            print(f"  未找到文件列表，尝试直接下载主文档...")
            # Fallback: try to download the primary document
            primary_url = base_url + primary_doc
            download_single_file(primary_url, filing_dir, primary_doc, headers)
            return
        
        print(f"  找到 {len(items)} 个文件:")
        
        for item in items:
            file_name = item.get('name', '')
            file_size = item.get('size', 0)
            file_type = item.get('type', '')
            
            print(f"    - {file_name} ({file_size} bytes, {file_type})")
            
            # Download each file
            file_url = base_url + file_name
            download_single_file(file_url, filing_dir, file_name, headers)
            
    except httpx.HTTPStatusError as e:
        print(f"  HTTP错误 {e.response.status_code}: {e}")
        # Fallback: try to get the primary document directly
        primary_url = base_url + primary_doc
        download_single_file(primary_url, filing_dir, primary_doc, headers)
    except Exception as e:
        print(f"  下载文件时发生错误: {e}")

def download_single_file(url: str, filing_dir: str, file_name: str, headers: dict):
    """
    Download a single file from SEC EDGAR.
    """
    try:
        response = httpx.get(url, headers=headers)
        response.raise_for_status()
        
        file_path = os.path.join(filing_dir, file_name)
        
        # Determine if the file is binary or text
        content_type = response.headers.get('content-type', '').lower()
        
        if 'text' in content_type or 'html' in content_type or 'xml' in content_type:
            # Text file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
        else:
            # Binary file
            with open(file_path, 'wb') as f:
                f.write(response.content)
        
        print(f"      ✓ 已下载: {file_name}")
        
    except httpx.HTTPStatusError as e:
        print(f"      ✗ 下载失败 {file_name}: HTTP {e.response.status_code}")
    except Exception as e:
        print(f"      ✗ 下载失败 {file_name}: {e}")

def extract_attachments_from_6k(filing_dir: str):
    """
    Extract and organize attachments from 6-K filings.
    """
    print(f"\n分析 {filing_dir} 中的附件...")
    
    # Look for the main 6-K document
    main_doc = None
    for file_name in os.listdir(filing_dir):
        if file_name.endswith('.htm') or file_name.endswith('.html'):
            file_path = os.path.join(filing_dir, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if '6-K' in content or 'FORM 6-K' in content:
                        main_doc = file_path
                        break
            except:
                continue
    
    if not main_doc:
        print("  未找到主要的6-K文档")
        return
    
    print(f"  主要文档: {os.path.basename(main_doc)}")
    
    # Parse the main document to find exhibits
    try:
        with open(main_doc, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # Look for exhibit references
        exhibits = []
        
        # Find all links that might be exhibits
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            link_text = link.get_text().strip()
            
            # Check if this looks like an exhibit
            if ('exhibit' in link_text.lower() or 
                'ex-' in href.lower() or 
                re.match(r'ex\d+', href, re.IGNORECASE)):
                exhibits.append({
                    'name': link_text,
                    'file': href
                })
        
        if exhibits:
            print(f"  找到 {len(exhibits)} 个附件:")
            for exhibit in exhibits:
                print(f"    - {exhibit['name']}: {exhibit['file']}")
        else:
            print("  未找到明确的附件引用")
            
    except Exception as e:
        print(f"  解析主文档时发生错误: {e}")

if __name__ == '__main__':
    # Example usage:
    ticker_symbol = input("请输入股票代码 (例如: BABA): ")
    if ticker_symbol:
        get_6k_filings_with_attachments(ticker_symbol)
        print("\n下载完成！") 