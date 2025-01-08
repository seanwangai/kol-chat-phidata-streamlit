import streamlit as st
from phi.model.google import GeminiOpenAIChat
from phi.model.deepseek import DeepSeekChat
from phi.agent import Agent


def test_gemini():
    """测试 Gemini API 连接和响应"""
    try:
        print("\n=== 测试 Gemini API ===")
        agent = Agent(
            model=GeminiOpenAIChat(
                id="gemini-2.0-flash-thinking-exp-1219",
                api_key=st.secrets["GOOGLE_API_KEY"],
            ),
            system_prompt="你是一个简单的测试助手。",
            markdown=True
        )
        test_message = "你好，这是一个测试消息。请回复：'测试成功'"
        print(f"发送测试消息: {test_message}")
        response = agent.run(test_message)
        result = response.content
        print(f"收到响应: {result}")
        return True, result
    except Exception as e:
        print(f"Gemini测试失败: {str(e)}")
        return False, str(e)


def test_deepseek():
    """测试 DeepSeek API 连接和响应"""
    try:
        print("\n=== 测试 DeepSeek API ===")
        agent = Agent(
            model=DeepSeekChat(
                api_key=st.secrets["DEEPSEEK_API_KEY"],
            ),
            system_prompt="你是一个简单的测试助手。",
            markdown=True
        )
        test_message = "你好，这是一个测试消息。请回复：'测试成功'"
        print(f"发送测试消息: {test_message}")
        response = agent.run(test_message)
        result = response.content
        print(f"收到响应: {result}")
        return True, result
    except Exception as e:
        print(f"DeepSeek测试失败: {str(e)}")
        return False, str(e)


if __name__ == "__main__":
    gemini_success, gemini_result = test_gemini()
    deepseek_success, deepseek_result = test_deepseek()

    print("\n=== 测试结果 ===")
    print(f"Gemini API: {'✅ 成功' if gemini_success else '❌ 失败'}")
    print(f"DeepSeek API: {'✅ 成功' if deepseek_success else '❌ 失败'}")
