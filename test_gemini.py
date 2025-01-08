import streamlit as st
from phi.model.google import GeminiOpenAIChat
from phi.model.deepseek import DeepSeekChat
from phi.agent import Agent
from itertools import cycle


def test_gemini_keys():
    """测试所有 Gemini API key 的可用性"""
    print("\n=== 测试 Gemini API Keys ===")
    results = []

    if "GOOGLE_API_KEYS" not in st.secrets:
        print("错误：未找到 GOOGLE_API_KEYS 配置")
        return False, "未找到 API Keys 配置"

    api_keys = st.secrets["GOOGLE_API_KEYS"]
    print(f"找到 {len(api_keys)} 个 API Keys")

    for i, api_key in enumerate(api_keys, 1):
        try:
            print(f"\n测试第 {i} 个 API Key: {api_key[:10]}...")
            agent = Agent(
                model=GeminiOpenAIChat(
                    id="gemini-2.0-flash-exp",
                    api_key=api_key,
                ),
                system_prompt="你是一个简单的测试助手。",
                markdown=True
            )
            test_message = "你好，这是一个测试消息。请回复：'测试成功'"
            response = agent.run(test_message)
            print(f"Key {i} 测试成功！响应: {response.content}")
            results.append((True, f"Key {i}"))
        except Exception as e:
            error_str = str(e)
            print(f"Key {i} 测试失败: {error_str}")
            results.append((False, f"Key {i}: {error_str}"))

    # 统计结果
    success_count = sum(1 for r in results if r[0])
    print(f"\n测试完成: {success_count}/{len(api_keys)} 个 Key 可用")

    # 返回详细结果
    return success_count > 0, "\n".join(f"{'✅' if r[0] else '❌'} {r[1]}" for r in results)


def test_key_rotation():
    """测试 API key 轮换机制"""
    print("\n=== 测试 API Key 轮换机制 ===")

    if "GOOGLE_API_KEYS" not in st.secrets:
        print("错误：未找到 GOOGLE_API_KEYS 配置")
        return False, "未找到 API Keys 配置"

    api_keys = st.secrets["GOOGLE_API_KEYS"]
    api_key_cycle = cycle(api_keys)

    try:
        # 测试连续请求，确保 key 正确轮换
        for i in range(len(api_keys) * 2):  # 测试两轮
            current_key = next(api_key_cycle)
            print(f"第 {i+1} 次请求使用 Key: {current_key[:10]}...")

            agent = Agent(
                model=GeminiOpenAIChat(
                    id="gemini-2.0-flash-exp",
                    api_key=current_key,
                ),
                system_prompt="你是一个简单的测试助手。",
                markdown=True
            )
            response = agent.run("测试轮换")
            print(f"请求成功，响应: {response.content[:30]}...")

        print("Key 轮换测试成功！")
        return True, "API Key 轮换机制正常"
    except Exception as e:
        error_str = str(e)
        print(f"轮换测试失败: {error_str}")
        return False, f"轮换测试失败: {error_str}"


def test_deepseek():
    """测试 DeepSeek API 连接和响应"""
    try:
        print("\n=== 测试 DeepSeek API ===")
        if "DEEPSEEK_API_KEY" not in st.secrets:
            print("错误：未找到 DEEPSEEK_API_KEY 配置")
            return False, "未找到 DeepSeek API Key 配置"

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
        error_str = str(e)
        print(f"DeepSeek测试失败: {error_str}")
        return False, str(e)


if __name__ == "__main__":
    print("\n🚀 开始 API 测试...\n")

    # 测试所有 Gemini API keys
    gemini_keys_success, gemini_keys_result = test_gemini_keys()

    # 测试 key 轮换机制
    # rotation_success, rotation_result = test_key_rotation()

    # 测试 DeepSeek
    deepseek_success, deepseek_result = test_deepseek()

    # 打印总结报告
    print("\n📊 测试结果总结")
    print("=" * 50)
    print(f"Gemini API Keys: {'✅ 通过' if gemini_keys_success else '❌ 失败'}")
    print(f"详细结果:\n{gemini_keys_result}")
    # print("-" * 50)
    # print(f"Key 轮换机制: {'✅ 通过' if rotation_success else '❌ 失败'}")
    # print(f"详细结果: {rotation_result}")
    print("-" * 50)
    print(f"DeepSeek API: {'✅ 通过' if deepseek_success else '❌ 失败'}")
    print(f"详细结果: {deepseek_result}")
    print("=" * 50)
