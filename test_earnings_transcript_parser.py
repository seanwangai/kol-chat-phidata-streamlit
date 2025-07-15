import requests
import json
from datetime import datetime
import re
from bs4 import BeautifulSoup
import html

def get_available_quarters(ticker: str, csrf_token: str = None):
    """
    获取指定公司所有可用的季度信息
    
    Args:
        ticker (str): 股票代码
        csrf_token (str): CSRF令牌
    
    Returns:
        list: 包含所有可用季度URL的列表
    """
    print(f"获取 {ticker} 的所有可用季度...")
    
    # 构建URL
    url = f"https://discountingcashflows.com/company/{ticker}/transcripts/?org.htmx.cache-buster=baseContent"
    
    # 请求头
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7,zh-CN;q=0.6,ja;q=0.5",
        "hx-boosted": "true",
        "hx-current-url": f"https://discountingcashflows.com/company/{ticker}/chart/",
        "hx-request": "true",
        "hx-target": "baseContent",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
    
    # 添加CSRF令牌
    if csrf_token:
        headers["x-csrftoken"] = csrf_token
    
    try:
        # 创建session
        session = requests.Session()
        
        # 发送请求
        response = session.get(url, headers=headers)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"错误: HTTP {response.status_code}")
            return []
        
        # 解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找所有包含transcripts链接的<a>标签
        transcript_links = []
        
        # 查找所有href属性包含transcripts/{年份}/{季度}/的链接
        pattern = re.compile(rf'/company/{ticker}/transcripts/(\d{{4}})/(\d+)/')
        
        for link in soup.find_all('a', href=pattern):
            href = link.get('href')
            if href and href != f'/company/{ticker}/transcripts/':  # 排除主页链接
                transcript_links.append(href)
        
        # 去重并排序
        transcript_links = list(set(transcript_links))
        transcript_links.sort(reverse=True)  # 按年份和季度倒序排列
        
        print(f"找到 {len(transcript_links)} 个可用季度:")
        for i, link in enumerate(transcript_links):
            # 从链接中提取年份和季度
            match = re.search(r'/(\d{4})/(\d+)/', link)
            if match:
                year, quarter = match.groups()
                print(f"  {i+1}. {year} Q{quarter} - {link}")
        
        return transcript_links
        
    except Exception as e:
        print(f"获取可用季度时发生错误: {e}")
        return []

def parse_transcript_url(url_path: str):
    """
    从URL路径中解析年份和季度信息
    
    Args:
        url_path (str): transcript URL路径, 例如 '/company/BABA/transcripts/2025/4/'
    
    Returns:
        tuple: (ticker, year, quarter) 或 None
    """
    pattern = r'/company/([A-Z]+)/transcripts/(\d{4})/(\d+)/'
    match = re.match(pattern, url_path)
    
    if match:
        ticker, year, quarter = match.groups()
        return ticker, int(year), quarter
    
    return None

def parse_html_transcript(html_content):
    """
    Parse HTML transcript content and extract structured data
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract fiscal year and date from the HTML
        fiscal_info = {}
        
        # Look for fiscal year information
        fiscal_span = soup.find('span', string=re.compile(r'Fiscal Year.*Quarter'))
        if fiscal_span:
            fiscal_text = fiscal_span.get_text()
            # Extract FY and Quarter info
            fy_match = re.search(r'Fiscal Year \(FY\) (\d+), Quarter (\d+)', fiscal_text)
            if fy_match:
                fiscal_info['fiscal_year'] = fy_match.group(1)
                fiscal_info['quarter'] = fy_match.group(2)
        
        # Look for date information
        date_span = soup.find('span', class_='text-xs')
        if date_span:
            date_text = date_span.get_text().strip()
            fiscal_info['date'] = date_text
        
        # Extract transcript content from textarea
        textarea = soup.find('textarea', id='AIInsightsContent')
        if not textarea:
            return None, fiscal_info
            
        # Parse the JSON content inside the textarea
        json_content = textarea.get_text()
        # Decode HTML entities
        json_content = html.unescape(json_content)
        
        try:
            transcript_data = json.loads(json_content)
            return transcript_data, fiscal_info
        except json.JSONDecodeError:
            print("Failed to parse JSON content from textarea")
            return None, fiscal_info
            
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return None, {}

def extract_speaker_content(transcript_content):
    """
    Extract speaker names and their content from the transcript
    """
    speakers_content = []
    
    # Split by common speaker patterns
    # Look for patterns like "Speaker Name: content" or "Speaker Name - content"
    lines = transcript_content.split('\n')
    current_speaker = None
    current_content = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if this line starts with a speaker name
        # Pattern: "Name: " or "Name - " at the beginning of line
        speaker_match = re.match(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[-:](.*)$', line)
        
        if speaker_match:
            # Save previous speaker's content if exists
            if current_speaker and current_content:
                speakers_content.append({
                    'speaker': current_speaker,
                    'content': ' '.join(current_content).strip()
                })
            
            # Start new speaker
            current_speaker = speaker_match.group(1).strip()
            current_content = [speaker_match.group(2).strip()] if speaker_match.group(2).strip() else []
        else:
            # Continue current speaker's content
            if current_speaker:
                current_content.append(line)
    
    # Don't forget the last speaker
    if current_speaker and current_content:
        speakers_content.append({
            'speaker': current_speaker,
            'content': ' '.join(current_content).strip()
        })
    
    return speakers_content

def save_raw_html(html_content, ticker, fiscal_info, quarter_num):
    """
    保存原始HTML文件到folder内
    
    Args:
        html_content (str): 原始HTML内容
        ticker (str): 股票代码
        fiscal_info (dict): 财政信息
        quarter_num (str): 季度编号
    
    Returns:
        str: 保存的HTML文件名
    """
    try:
        # 创建文件夹（如果不存在）
        import os
        folder_name = f"{ticker}_transcripts"
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            print(f"创建文件夹: {folder_name}")
        
        # 生成HTML文件名
        html_filename = f"{folder_name}/transcript_{ticker}_FY{fiscal_info.get('fiscal_year', 'UNKNOWN')}_Q{quarter_num}.html"
        
        # 保存HTML文件
        with open(html_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"原始HTML已保存到: {html_filename}")
        return html_filename
        
    except Exception as e:
        print(f"保存HTML文件时发生错误: {e}")
        return None

def save_transcript_as_txt(transcript_data, fiscal_info, filename):
    """
    Save the parsed transcript as a clean TXT file
    """
    try:
        # 创建文件夹（如果不存在）
        import os
        ticker = transcript_data.get('symbol', 'UNKNOWN')
        folder_name = f"{ticker}_transcripts"
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
            print(f"创建文件夹: {folder_name}")
        
        # 修改文件名路径，放到文件夹内
        txt_filename = f"{folder_name}/{filename}"
        
        with open(txt_filename, 'w', encoding='utf-8') as f:
            # Write header information
            f.write("="*60 + "\n")
            f.write("EARNINGS CALL TRANSCRIPT\n")
            f.write("="*60 + "\n\n")
            
            # Write fiscal information
            if fiscal_info:
                f.write(f"Company: {transcript_data.get('symbol', 'N/A')}\n")
                f.write(f"Fiscal Year: {fiscal_info.get('fiscal_year', 'N/A')}\n")
                f.write(f"Quarter: {fiscal_info.get('quarter', 'N/A')}\n")
                f.write(f"Date: {fiscal_info.get('date', 'N/A')}\n")
                f.write(f"Transcript Date: {transcript_data.get('date', 'N/A')}\n")
                f.write("\n" + "="*60 + "\n\n")
            
            # Extract and write speaker content
            content = transcript_data.get('content', '')
            speakers_content = extract_speaker_content(content)
            
            if speakers_content:
                for item in speakers_content:
                    f.write(f"[{item['speaker']}]\n")
                    f.write(f"{item['content']}\n\n")
                    f.write("-" * 40 + "\n\n")
            else:
                # Fallback: write raw content if speaker extraction fails
                f.write("RAW TRANSCRIPT CONTENT:\n")
                f.write("-" * 40 + "\n")
                f.write(content)
        
        print(f"Transcript saved to: {txt_filename}")
        return txt_filename
        
    except Exception as e:
        print(f"Error saving transcript: {e}")
        return None

def get_earnings_transcript(quarter: str, ticker: str, year: int, csrf_token: str = None):
    """Get the earnings transcripts using the correct URL format

    Args:
        quarter (str): Quarter number (e.g., "1", "2", "3", "4")
        ticker (str): Stock ticker symbol
        year (int): Year
        csrf_token (str): CSRF token for authentication
    """
    print(f"Fetching earnings transcript for {ticker} Q{quarter} {year}...")
    
    # Convert quarter to number format
    quarter_num = quarter.replace('Q', '') if quarter.startswith('Q') else quarter
    
    # Build the URL based on the actual format
    url = f"https://discountingcashflows.com/company/{ticker}/transcripts/{year}/{quarter_num}/"
    
    # Add cache buster parameter
    cache_buster_url = f"{url}?org.htmx.cache-buster=transcriptsContent"
    
    # Headers based on the actual browser request
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7,zh-CN;q=0.6,ja;q=0.5",
        "hx-boosted": "true",
        "hx-current-url": f"https://discountingcashflows.com/company/{ticker}/transcripts/{year}/{quarter_num}/",
        "hx-request": "true",
        "hx-target": "transcriptsContent",
        "priority": "u=1, i",
        "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    }
    
    # Add CSRF token if provided
    if csrf_token:
        headers["x-csrftoken"] = csrf_token
    
    try:
        # Create a session to handle cookies
        session = requests.Session()
        
        # First, try to get the main page to establish session
        main_page_url = f"https://discountingcashflows.com/company/{ticker}/transcripts/{year}/{quarter_num}/"
        print(f"Getting main page: {main_page_url}")
        
        main_response = session.get(main_page_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        })
        
        print(f"Main page response status: {main_response.status_code}")
        
        # Try to extract CSRF token from the main page if not provided
        if not csrf_token and main_response.status_code == 200:
            csrf_match = re.search(r'csrftoken["\']?\s*:\s*["\']([^"\']+)["\']', main_response.text)
            if not csrf_match:
                csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']', main_response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
                headers["x-csrftoken"] = csrf_token
                print(f"Extracted CSRF token: {csrf_token[:20]}...")
        
        # Now make the actual request for transcript data
        print(f"Making transcript request: {cache_buster_url}")
        response = session.get(cache_buster_url, headers=headers)
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}")
            return None
        
        # Parse the HTML response
        transcript_data, fiscal_info = parse_html_transcript(response.text)
        
        if transcript_data:
            # Save as TXT file
            filename = f"transcript_{ticker}_FY{fiscal_info.get('fiscal_year', year)}_Q{quarter_num}.txt"
            txt_filename = save_transcript_as_txt(transcript_data, fiscal_info, filename)
            
            # Save raw HTML file
            html_filename = save_raw_html(response.text, ticker, fiscal_info, quarter_num)
            
            # Return structured data
            return {
                'ticker': ticker,
                'quarter': f"Q{quarter_num}",
                'year': year,
                'fiscal_year': fiscal_info.get('fiscal_year'),
                'date': fiscal_info.get('date'),
                'transcript_date': transcript_data.get('date'),
                'content': transcript_data.get('content'),
                'parsed_successfully': True,
                'txt_filename': txt_filename,
                'html_filename': html_filename
            }
        else:
            print("Failed to parse transcript data from HTML")
            return None
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def get_earnings_transcript_from_url(url_path: str, csrf_token: str = None):
    """
    从URL路径获取财报电话会议记录
    
    Args:
        url_path (str): transcript URL路径, 例如 '/company/BABA/transcripts/2025/4/'
        csrf_token (str): CSRF令牌
    
    Returns:
        dict: 解析后的transcript数据
    """
    # 解析URL获取参数
    parsed = parse_transcript_url(url_path)
    if not parsed:
        print(f"无法解析URL: {url_path}")
        return None
    
    ticker, year, quarter = parsed
    print(f"从URL获取财报记录: {ticker} {year} Q{quarter}")
    
    # 调用原有函数
    return get_earnings_transcript(quarter, ticker, year, csrf_token)

def parse_existing_html_file(html_filename):
    """
    Parse an existing HTML file and extract transcript data
    """
    try:
        with open(html_filename, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        transcript_data, fiscal_info = parse_html_transcript(html_content)
        
        if transcript_data:
            # Generate filename based on the data
            ticker = transcript_data.get('symbol', 'UNKNOWN')
            fy = fiscal_info.get('fiscal_year', 'UNKNOWN')
            quarter = fiscal_info.get('quarter', 'UNKNOWN')
            
            filename = f"transcript_{ticker}_FY{fy}_Q{quarter}.txt"
            
            if save_transcript_as_txt(transcript_data, fiscal_info, filename):
                print(f"Successfully parsed and saved: {filename}")
                return {
                    'ticker': ticker,
                    'fiscal_year': fy,
                    'quarter': quarter,
                    'date': fiscal_info.get('date'),
                    'transcript_date': transcript_data.get('date'),
                    'txt_filename': filename,
                    'parsed_successfully': True
                }
            else:
                print("Failed to save transcript")
                return None
        else:
            print("Failed to parse transcript data")
            return None
            
    except Exception as e:
        print(f"Error parsing HTML file: {e}")
        return None

if __name__ == "__main__":
    print("财报电话会议记录解析器")
    print("="*50)
    
    # 第一步：获取所有可用的季度
    print("第一步：获取所有可用季度...")
    ticker = "AAPL"
    available_quarters = get_available_quarters(ticker)
    
    if available_quarters:
        print(f"\n成功获取到 {len(available_quarters)} 个可用季度")
        
        # 获取最近4个季度的transcript
        print(f"\n第二步：获取最近4个季度的transcript...")
        for i, url in enumerate(available_quarters[:4]):
            print(f"\n--- 获取第 {i+1} 个季度 ---")
            print(f"选择的URL: {url}")
            
            # 获取transcript
            transcript = get_earnings_transcript_from_url(url)
            
            if transcript:
                print("\n" + "="*50)
                print("获取结果:")
                print("="*50)
                print(f"公司: {transcript['ticker']}")
                print(f"财政年度: {transcript['fiscal_year']}")
                print(f"季度: {transcript['quarter']}")
                print(f"日期: {transcript['date']}")
                print(f"输出文件 (TXT): {transcript['txt_filename']}")
                if transcript.get('html_filename'):
                    print(f"输出文件 (HTML): {transcript['html_filename']}")
                print(f"状态: {'成功' if transcript['parsed_successfully'] else '失败'}")
            else:
                print("获取transcript失败")
            
            # 友好起见，在请求之间稍作停顿
            if i < 3: # 如果不是最后一个，就等待
                import time
                print("\n等待2秒钟...")
                time.sleep(2)
                
    else:
        print("未能获取到可用季度信息")
    
    # 保留原有的HTML文件解析功能
    print("\n" + "="*50)
    print("解析现有HTML文件: transcript_BABA_Q2_2023.html")
    result = parse_existing_html_file("transcript_BABA_Q2_2023.html")
    
    if result:
        print("\n" + "="*50)
        print("解析结果:")
        print("="*50)
        print(f"公司: {result['ticker']}")
        print(f"财政年度: {result['fiscal_year']}")
        print(f"季度: {result['quarter']}")
        print(f"日期: {result['date']}")
        print(f"输出文件: {result['txt_filename']}")
        print(f"状态: {'成功' if result['parsed_successfully'] else '失败'}")
    else:
        print("解析现有HTML文件失败") 