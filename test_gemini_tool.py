import base64
import os
import sys
from google import genai
from google.genai import types
import streamlit as st


def test_gemini_search():
    """测试 Gemini 搜索工具功能"""
    print("\n=== 测试 Gemini 搜索工具 ===")
    
    # 检查环境变量中是否有API密钥
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 如果环境变量中没有，尝试从streamlit secrets获取
    if not api_key and "GOOGLE_API_KEYS" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEYS"][0]  # 使用第一个密钥
        print("使用Streamlit secrets中的API密钥")
    
    if not api_key:
        print("错误：未找到GEMINI_API_KEY环境变量或Streamlit secrets配置")
        return False, "未找到API密钥配置"
    
    # 设置环境变量供genai库使用
    os.environ["GEMINI_API_KEY"] = api_key
    
    try:
        print(f"使用API密钥: {api_key[:10]}...")
        
        # 初始化Gemini客户端
        client = genai.Client(api_key=api_key)
        
        # 测试查询
        test_queries = [
            "2025年1月 快手電商 近況？ 根據時間利列點 用中文回答",
            "2025年2月 deepseek 近況？ 根據時間利列點 用中文回答",
            "2025年2月 騰訊元寶 近況？ 根據時間利列點 用中文回答"
        ]
        
        results = []
        
        for i, query in enumerate(test_queries, 1):
            try:
                print(f"\n测试查询 {i}: '{query}'")
                
                # 配置模型和工具
                model = "gemini-2.0-flash"
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=query)
                        ],
                    ),
                ]
                tools = [
                    types.Tool(google_search=types.GoogleSearch())
                ]
                generate_content_config = types.GenerateContentConfig(
                    temperature=1,
                    top_p=0.95,
                    top_k=40,
                    max_output_tokens=8192,
                    tools=tools,
                    response_mime_type="text/plain",
                )
                
                # 执行查询
                print("正在执行搜索查询...")
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                )
                
                # 输出结果
                result = response.text
                print(f"查询成功！响应长度: {len(result)} 字符")
                # print(f"响应预览: {result[:100]}...")
                print(f"响应预览: {result}...")
                results.append((True, f"查询 {i}: '{query}'"))
                
            except Exception as e:
                error_str = str(e)
                print(f"查询 {i} 失败: {error_str}")
                results.append((False, f"查询 {i}: {error_str}"))
        
        # 统计结果
        success_count = sum(1 for r in results if r[0])
        print(f"\n测试完成: {success_count}/{len(test_queries)} 个查询成功")
        
        # 返回详细结果
        return success_count > 0, "\n".join(f"{'✅' if r[0] else '❌'} {r[1]}" for r in results)
        
    except Exception as e:
        error_str = str(e)
        print(f"测试失败: {error_str}")
        return False, f"测试失败: {error_str}"


def test_gemini_search_stream():
    """测试 Gemini 搜索工具的流式输出功能"""
    print("\n=== 测试 Gemini 搜索工具流式输出 ===")
    
    # 检查环境变量中是否有API密钥
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 如果环境变量中没有，尝试从streamlit secrets获取
    if not api_key and "GOOGLE_API_KEYS" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEYS"][0]  # 使用第一个密钥
        print("使用Streamlit secrets中的API密钥")
    
    if not api_key:
        print("错误：未找到GEMINI_API_KEY环境变量或Streamlit secrets配置")
        return False, "未找到API密钥配置"
    
    # 设置环境变量供genai库使用
    os.environ["GEMINI_API_KEY"] = api_key
    
    try:
        print(f"使用API密钥: {api_key[:10]}...")
        
        # 初始化Gemini客户端
        client = genai.Client(api_key=api_key)
        
        # 测试查询
        query = "请简要介绍一下人工智能的发展历史"
        
        print(f"\n测试流式查询: '{query}'")
        
        # 配置模型和工具
        model = "gemini-2.0-flash"
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=query)
                ],
            ),
        ]
        tools = [
            types.Tool(google_search=types.GoogleSearch())
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            tools=tools,
            response_mime_type="text/plain",
        )
        
        # 执行流式查询
        print("正在执行流式搜索查询...")
        print("\n响应内容:")
        print("-" * 50)
        
        char_count = 0
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            chunk_text = chunk.text
            char_count += len(chunk_text)
            print(chunk_text, end="")
            sys.stdout.flush()  # 确保输出立即显示
        
        print("\n" + "-" * 50)
        print(f"流式输出完成，总共 {char_count} 个字符")
        
        return True, "流式搜索查询测试成功"
        
    except Exception as e:
        error_str = str(e)
        print(f"流式测试失败: {error_str}")
        return False, f"流式测试失败: {error_str}"


def generate_with_custom_query(query):
    """使用自定义查询测试Gemini搜索工具"""
    print(f"\n=== 使用自定义查询测试Gemini搜索工具 ===")
    print(f"查询: '{query}'")
    
    # 检查环境变量中是否有API密钥
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # 如果环境变量中没有，尝试从streamlit secrets获取
    if not api_key and "GOOGLE_API_KEYS" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEYS"][0]  # 使用第一个密钥
        print("使用Streamlit secrets中的API密钥")
    
    if not api_key:
        print("错误：未找到GEMINI_API_KEY环境变量或Streamlit secrets配置")
        return
    
    # 设置环境变量供genai库使用
    os.environ["GEMINI_API_KEY"] = api_key
    
    try:
        # 初始化Gemini客户端
        client = genai.Client(api_key=api_key)
        
        # 配置模型和工具
        model = "gemini-2.0-flash"
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=query)
                ],
            ),
        ]
        tools = [
            types.Tool(google_search=types.GoogleSearch())
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            tools=tools,
            response_mime_type="text/plain",
        )
        
        # 执行流式查询
        print("正在执行流式搜索查询...")
        print("\n响应内容:")
        print("-" * 50)
        
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            print(chunk.text, end="")
            sys.stdout.flush()  # 确保输出立即显示
        
        print("\n" + "-" * 50)
        
    except Exception as e:
        error_str = str(e)
        print(f"查询失败: {error_str}")


if __name__ == "__main__":
    print("\n🚀 开始 Gemini 搜索工具测试...\n")
    
    # 测试基本搜索功能
    search_success, search_result = test_gemini_search()
    
    # 测试流式输出
    stream_success, stream_result = test_gemini_search_stream()
    
    # 如果命令行参数中有查询，则使用自定义查询测试
    if len(sys.argv) > 1:
        custom_query = " ".join(sys.argv[1:])
        generate_with_custom_query(custom_query)
    
    # 打印总结报告
    print("\n📊 测试结果总结")
    print("=" * 50)
    print(f"Gemini 搜索功能: {'✅ 通过' if search_success else '❌ 失败'}")
    print(f"详细结果:\n{search_result}")
    print("-" * 50)
    print(f"Gemini 流式输出: {'✅ 通过' if stream_success else '❌ 失败'}")
    print(f"详细结果: {stream_result}")
    print("=" * 50)
    
    print("\n💡 提示: 你可以通过命令行参数提供自定义查询，例如:")
    print("python test_gemini_tool.py 请介绍一下量子计算的最新进展")