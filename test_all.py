import os
import time
import json
import datetime
from itertools import cycle
from collections import Counter
import concurrent.futures
import random
import backoff
import httpx
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from exa_py import Exa
# from firecrawl import App
from google import genai
from pathlib import Path

print("=== 开始测试所有API功能 ===\n")

# 加载环境变量或密钥
try:
    # 尝试加载.streamlit/secrets.toml
    import streamlit as st
    secrets_available = True
    print("已加载Streamlit密钥")
except:
    # 如果无法加载，则尝试从环境变量获取
    secrets_available = False
    print("无法加载Streamlit密钥，将尝试从环境变量获取")

# API密钥管理
class APIKeyManager:
    def __init__(self):
        self.api_keys = {
            "google": self._get_api_keys("GOOGLE_API_KEYS"),
            "exa": self._get_api_keys("EXA_API_KEYS"),
            "firecrawl": self._get_api_keys("FIRECRAWL_API_KEYS")
        }
        self.api_key_cycles = {
            "google": cycle(self.api_keys["google"]),
            "exa": cycle(self.api_keys["exa"]),
            "firecrawl": cycle(self.api_keys["firecrawl"])
        }
    
    def _get_api_keys(self, key_name):
        if secrets_available:
            # 从Streamlit密钥获取
            try:
                return st.secrets[key_name]
            except:
                print(f"警告: 在Streamlit密钥中未找到 {key_name}")
                return []
        else:
            # 从环境变量获取
            env_key = os.environ.get(key_name)
            if env_key:
                # 假设环境变量中的键以逗号分隔
                return env_key.split(",")
            else:
                print(f"警告: 在环境变量中未找到 {key_name}")
                return []
    
    def get_next_key(self, api_type):
        try:
            keys = self.api_keys[api_type]
            if not keys:
                raise ValueError(f"没有可用的{api_type} API密钥")
            
            return next(self.api_key_cycles[api_type])
        except Exception as e:
            print(f"获取{api_type} API密钥时出错: {str(e)}")
            return None
    
    def test_all_keys(self):
        """测试所有API密钥的有效性"""
        results = {}
        
        # 测试Google API密钥
        google_results = []
        for i, key in enumerate(self.api_keys["google"]):
            masked_key = f"{key[:5]}...{key[-4:]}"
            try:
                # 简单验证密钥格式
                if not key.startswith("AIza"):
                    google_results.append({"key": masked_key, "status": "无效", "error": "格式不正确"})
                    continue
                
                # 创建客户端对象测试
                client = genai.Client(api_key=key)
                # 尝试列出模型（轻量操作）
                models = client.list_models()
                if models:
                    google_results.append({"key": masked_key, "status": "有效"})
                else:
                    google_results.append({"key": masked_key, "status": "无效", "error": "无法列出模型"})
            except Exception as e:
                google_results.append({"key": masked_key, "status": "无效", "error": str(e)})
        
        # 测试Exa API密钥
        exa_results = []
        for i, key in enumerate(self.api_keys["exa"]):
            masked_key = f"{key[:5]}...{key[-4:]}"
            try:
                # 创建客户端对象测试
                client = Exa(api_key=key)
                # 尝试进行一个简单搜索
                result = client.search("test", num_results=1)
                if result:
                    exa_results.append({"key": masked_key, "status": "有效"})
                else:
                    exa_results.append({"key": masked_key, "status": "无效", "error": "无法执行搜索"})
            except Exception as e:
                exa_results.append({"key": masked_key, "status": "无效", "error": str(e)})
        
        # # 测试Firecrawl API密钥
        # firecrawl_results = []
        # for i, key in enumerate(self.api_keys["firecrawl"]):
        #     masked_key = f"{key[:5]}...{key[-4:]}"
        #     try:
        #         # 创建客户端对象测试
        #         client = FirecrawlApp(api_key=key)
        #         # 尝试获取一个简单网站的信息
        #         result = client.map_url("https://example.com")
        #         if result:
        #             firecrawl_results.append({"key": masked_key, "status": "有效"})
        #         else:
        #             firecrawl_results.append({"key": masked_key, "status": "无效", "error": "无法映射URL"})
        #     except Exception as e:
        #         firecrawl_results.append({"key": masked_key, "status": "无效", "error": str(e)})
        
        # 汇总结果
        results["google"] = google_results
        results["exa"] = exa_results
        # results["firecrawl"] = firecrawl_results
        
        return results

# 初始化API密钥管理器
api_manager = APIKeyManager()

# 辅助函数
def estimate_tokens(text):
    """估算文本的token数量（粗略估计，使用简单公式）"""
    words = text.split()
    return int(len(words) * 1.3)

def format_date_for_api(date):
    """转换为UTC时间格式"""
    return date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def generate_quarter_ranges():
    """生成从2024年至今的季度时间范围"""
    quarters = []
    
    # 起始日期：2024年1月1日
    start_date = datetime(2024, 1, 1)
    # 结束日期：当前日期
    end_date = datetime.now()
    
    current_date = start_date
    while current_date < end_date:
        # 计算当前季度的结束日期
        if current_date.month in [1, 2, 3]:
            quarter_end = datetime(current_date.year, 3, 31, 23, 59, 59, 999999)
        elif current_date.month in [4, 5, 6]:
            quarter_end = datetime(current_date.year, 6, 30, 23, 59, 59, 999999)
        elif current_date.month in [7, 8, 9]:
            quarter_end = datetime(current_date.year, 9, 30, 23, 59, 59, 999999)
        else:
            quarter_end = datetime(current_date.year, 12, 31, 23, 59, 59, 999999)
        
        # 如果季度结束日期超过了当前日期，使用当前日期作为结束
        if quarter_end > end_date:
            quarter_end = end_date
            
        quarters.append({
            'start': current_date,
            'end': quarter_end,
            'name': f"{current_date.year}Q{(current_date.month-1)//3+1}"
        })
        
        # 移动到下一个季度的第一天
        current_date = (quarter_end + timedelta(days=1))
        
    return quarters

# 1. 测试Gemini API功能
def test_gemini_api():
    print("\n=== 测试Gemini API ===")
    
    # 获取API密钥
    api_key = api_manager.get_next_key("google")
    if not api_key:
        print("无法获取Gemini API密钥，跳过测试")
        return False
    
    try:
        print(f"使用API密钥: {api_key[:5]}...{api_key[-4:]}")
        
        # 创建客户端
        client = genai.Client(api_key=api_key)
        
        # 准备内容
        system_prompt = "你是一位专业的金融分析师，专注于发现企业财务风险和欺诈行为。"
        user_query = "请分析阿里巴巴公司最近的财务状况和潜在风险。"
        
        combined_prompt = f"{system_prompt}\n\n{user_query}"
        
        # 记录提示统计
        prompt_chars = len(combined_prompt)
        prompt_tokens = estimate_tokens(combined_prompt)
        print(f"提示总字数: {prompt_chars:,} 字符")
        print(f"提示估计Token数: 约 {prompt_tokens:,} tokens")
        
        # 准备请求内容
        from google.genai import types
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=combined_prompt)],
            ),
        ]
        
        # 配置生成参数
        generate_content_config = types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.95,
            top_k=40,
            max_output_tokens=4096,
            response_mime_type="text/plain",
        )
        
        # 定义带退避策略的重试函数
        @backoff.on_exception(
            backoff.expo, 
            (Exception, httpx.ConnectError, httpx.ReadTimeout), 
            max_tries=3,
            factor=2,
            jitter=backoff.full_jitter
        )
        def generate_with_retry():
            # 随机暂停一小段时间，避免并发请求过多
            time.sleep(random.uniform(0.5, 2.0))
            
            try:
                # 不使用timeout参数，改用线程池实现超时机制
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=contents,
                    config=generate_content_config,
                )
                return response
            except Exception as e:
                print(f"生成内容错误: {str(e)}")
                raise
        
        # 使用线程池和Future实现超时控制
        def execute_with_timeout(func, timeout_seconds=30):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                # 提交任务到线程池
                future = executor.submit(func)
                try:
                    # 等待结果，设置超时时间
                    print(f"等待响应，超时时间: {timeout_seconds}秒")
                    start_time = time.time()
                    # 简单实现倒计时显示
                    while not future.done() and time.time() - start_time < timeout_seconds:
                        remaining = timeout_seconds - (time.time() - start_time)
                        print(f"\r⏱️ 等待响应: {remaining:.0f}秒", end="", flush=True)
                        time.sleep(1)
                    
                    if future.done():
                        print("\r⏱️ 收到响应!       ")
                        return future.result()
                    else:
                        print("\r⏱️ 响应超时!       ")
                        # 超时处理
                        raise TimeoutError(f"操作超时（超过{timeout_seconds}秒）")
                except concurrent.futures.TimeoutError:
                    print("\r⏱️ 响应超时!       ")
                    raise TimeoutError(f"操作超时（超过{timeout_seconds}秒）")
        
        # 尝试执行API调用，最多重试3次
        max_retries = 3
        retry_count = 0
        response = None
        
        while response is None and retry_count < max_retries:
            try:
                # 使用超时控制执行API调用
                response = execute_with_timeout(generate_with_retry, 30)
            except (TimeoutError, Exception) as e:
                retry_count += 1
                print(f"\n尝试 {retry_count}/{max_retries} 失败: {str(e)}")
                
                if retry_count < max_retries:
                    print(f"将在1秒后重试...")
                    time.sleep(1)
                else:
                    print("最大重试次数已达到")
                    raise Exception(f"在 {max_retries} 次尝试后仍然失败: {str(e)}")
        
        if response:
            # 获取结果
            result_text = response.text
            
            # 记录输出结果统计
            output_chars = len(result_text)
            output_tokens = estimate_tokens(result_text)
            print(f"输出结果总字数: {output_chars:,} 字符")
            print(f"输出结果估计Token数: 约 {output_tokens:,} tokens")
            print(f"总Token消耗: 约 {prompt_tokens + output_tokens:,} tokens")
            
            # 显示部分输出
            preview = result_text[:500] + ("..." if len(result_text) > 500 else "")
            print(f"\nGemini API输出预览:\n{preview}")
            
            print("\nGemini API测试成功！")
            return True
        else:
            raise Exception("无法获取响应")
    
    except Exception as e:
        print(f"Gemini API测试失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

# 2. 测试Exa搜索功能
def test_exa_search():
    print("\n=== 测试Exa搜索 ===")
    
    # 获取API密钥
    api_key = api_manager.get_next_key("exa")
    if not api_key:
        print("无法获取Exa API密钥，跳过测试")
        return False
    
    try:
        print(f"使用API密钥: {api_key[:5]}...{api_key[-4:]}")
        
        # 创建客户端
        exa_client = Exa(api_key=api_key)
        
        # 准备搜索参数
        keyword = "阿里巴巴 业绩"
        
        # 当前季度的日期范围
        now = datetime.now()
        quarter_start = datetime(now.year, ((now.month-1)//3)*3+1, 1)
        quarter_end = now
        
        # 格式化日期
        formatted_start = format_date_for_api(quarter_start)
        formatted_end = format_date_for_api(quarter_end)
        
        print(f"搜索关键词: {keyword}")
        print(f"搜索时间范围: {quarter_start.strftime('%Y-%m-%d')} 至 {quarter_end.strftime('%Y-%m-%d')}")
        
        # 执行搜索
        result = exa_client.search(
            keyword,
            type="keyword",
            num_results=1,
            start_published_date=formatted_start,
            end_published_date=formatted_end,
            # text={
            #     "max_characters": 5000
            # }
        )
        
        # 处理结果
        search_results = []
        contents = []
        
        # 尝试获取结果
        if hasattr(result, 'results'):
            search_results = result.results
        elif hasattr(result, 'data') and hasattr(result.data, 'results'):
            search_results = result.data.results
        elif hasattr(result, 'to_dict'):
            result_dict = result.to_dict()
            if 'data' in result_dict and 'results' in result_dict['data']:
                search_results = result_dict['data']['results']
        elif isinstance(result, dict):
            if 'data' in result and 'results' in result['data']:
                search_results = result['data']['results']
            elif 'results' in result:
                search_results = result['results']
        
        # 从结果中提取内容
        for item in search_results:
            content = None
            url = None
            
            # 尝试获取内容
            if hasattr(item, 'text') and item.text:
                content = item.text
            elif isinstance(item, dict) and 'text' in item and item['text']:
                content = item['text']
            
            # 尝试获取URL
            if hasattr(item, 'url'):
                url = item.url
            elif isinstance(item, dict) and 'url' in item:
                url = item['url']
            
            # 添加到结果中
            if content and url:
                contents.append({
                    'url': url,
                    'content': content
                })
        
        # 显示结果统计
        print(f"获取到搜索结果: {len(search_results)} 条")
        print(f"获取到内容: {len(contents)} 个")
        
        # 显示部分搜索结果
        if contents:
            print("\nExa搜索结果预览:")
            for i, item in enumerate(contents[:2]):
                print(f"\n- 结果 {i+1}: {item['url']}")
                preview = item['content'][:200] + ("..." if len(item['content']) > 200 else "")
                print(f"  {preview}")
        
        print("\nExa搜索测试成功！")
        return True
    
    except Exception as e:
        print(f"Exa搜索测试失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

# 3. 测试Firecrawl功能
# def test_firecrawl():
#     print("\n=== 测试Firecrawl ===")
    
#     try:
#         # 使用指定的API密钥
#         api_key = 'fc-15209a3576e04246af1f273702ea8137'
#         print(f"使用API密钥: {api_key[:5]}...{api_key[-4:]}")
        
#         # 创建客户端
#         firecrawl_client = FirecrawlApp(api_key=api_key)
        
#         # 使用指定的URL
#         url = 'https://xueqiu.com/S/BABA/324257037?md5__1038=n4%2Bx9DRDnAKEe0%3DD%2FD0QpQWcxfxmq0QaY74D'
        
#         print(f"抓取URL: {url}")
        
#         # 根据API文档，使用scrape_url方法抓取内容
#         print("使用scrape_url方法抓取内容...")
        
#         # 使用指定的参数格式
#         scrape_result = firecrawl_client.scrape_url(
#             url=url, 
#             params={
#                 'formats': ['markdown'],
#             }
#         )
        
#         # 打印原始返回结果结构
#         print("\n原始返回结果结构:")
#         print(f"类型: {type(scrape_result)}")
#         if isinstance(scrape_result, dict):
#             print("字典键:", list(scrape_result.keys()))
            
#         # 检查结果格式是否符合预期
#         success = False
#         content = ""
        
#         # 预期的返回结构
#         # {
#         #       "markdown": "# Markdown Content",
#         #       "metadata": {
#         #         "title": "标题",
#         #         "description": "描述",
#         #         "language": null,
#         #         "sourceURL": "URL"
#         #       }
#         # }
        
#         if isinstance(scrape_result, dict):
#             print('md')
#             print(scrape_result.get('markdown'))
#             if scrape_result.get('markdown'):
#                 content = scrape_result['markdown']
#                 success = True
                    
#                 # 打印元数据
#                 if 'metadata' in scrape_result:
#                     metadata = scrape_result['metadata']
#                     print("\n元数据:")
#                     print(f"标题: {metadata.get('title', '无')}")
#                     print(f"描述: {metadata.get('description', '无')}")
#                     print(f"源URL: {metadata.get('sourceURL', '无')}")
        
#         if success:
#             content_length = len(content) if isinstance(content, str) else 0
#             print(f"\n成功抓取，内容长度: {content_length} 字符")
            
#             # 显示内容预览
#             if content_length > 0:
#                 preview = content[:500] + ("..." if content_length > 500 else "")
#                 print(f"\nMarkdown内容预览:\n{preview}")
            
#             print("\nFirecrawl测试成功！")
#             return True
#         else:
#             print(f"\n无法解析Firecrawl响应或返回格式不符合预期")
#             print(f"返回内容: {scrape_result}")
#             return False
    
#     except Exception as e:
#         print(f"Firecrawl测试失败: {str(e)}")
#         import traceback
#         print(traceback.format_exc())
#         return False

# 运行所有测试
def run_all_tests():
    # 简单打印所有API密钥
    print("\n=== API密钥列表 ===")
    
    # 打印Google API密钥
    print("\nGOOGLE_API_KEYS:")
    for i, key in enumerate(api_manager.api_keys["google"]):
        masked_key = f"{key[:5]}...{key[-4:]}" if len(key) > 10 else "无效密钥"
        print(f"{i+1}. {masked_key}")
    
    # 打印Exa API密钥
    print("\nEXA_API_KEYS:")
    for i, key in enumerate(api_manager.api_keys["exa"]):
        masked_key = f"{key[:5]}...{key[-4:]}" if len(key) > 10 else "无效密钥"
        print(f"{i+1}. {masked_key}")
    
    # 打印Firecrawl API密钥
    print("\nFIRECRAWL_API_KEYS:")
    for i, key in enumerate(api_manager.api_keys["firecrawl"]):
        masked_key = f"{key[:5]}...{key[-4:]}" if len(key) > 10 else "无效密钥"
        print(f"{i+1}. {masked_key}")
    
    # 然后运行功能测试
    print("\n=== 运行功能测试 ===")
    
    results = {
        "gemini": test_gemini_api(),
        "exa": test_exa_search(),
        # "firecrawl": test_firecrawl()
    }
    
    print("\n=== 测试结果摘要 ===")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    # 返回所有测试是否都成功
    return all(results.values())

if __name__ == "__main__":
    run_all_tests() 