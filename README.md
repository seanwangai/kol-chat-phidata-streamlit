# AI 智能对话系统

一个基于多种 AI 模型的智能对话系统，支持专家知识库问答和纯对话模式。

## 功能特点

### 1. 多页面支持
- `/` - 专家知识库问答系统
- `/chat` - 纯对话模式

### 2. 模型支持
- Gemini Flash Thinking (gemini-2.0-flash-thinking-exp-1219)
- Gemini Flash (gemini-2.0-flash-exp)
- Gemini 1206 (gemini-exp-1206)
- DeepSeek

### 3. 专家系统（首页）
- 动态加载专家知识库
- 支持多专家同时回答
- 自动生成专家观点总结
- 支持专家选择和全选/取消全选
- 支持更新专家资料
- 支持 KOL 模式和问答模式切换

### 4. 纯对话模式（/chat）
- 简洁的对话界面
- 支持模型切换
- 默认使用 Gemini Flash Thinking
- 支持清空对话历史
- 实时显示系统状态

### 5. 图片处理
- 支持图片上传（Gemini 模型）
- 支持图片分析和问答
- 自动在历史记录中保存图片

### 6. API 管理
- 多 API Key 轮换机制
- 自动处理配额限制（429错误）
- 智能重试机制
- 错误状态显示

### 7. 文件支持
- PDF 文件解析
- EPUB 文件解析
- TXT 文件解析
- DOCX 文件解析

### 8. 数据管理
- Dropbox 集成
- 自动下载和更新专家资料
- 本地缓存管理
- 会话状态持久化

## 使用方法

### 环境配置
1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置 API Keys（.streamlit/secrets.toml）：
```toml
GOOGLE_API_KEYS = [
    "your-key-1",
    "your-key-2",
    "your-key-3"
]
DEEPSEEK_API_KEY = "your-deepseek-key"
```

3. 配置 Dropbox（可选）：
```toml
DROPBOX_DATA_URL = "your-dropbox-url"
DROPBOX_DATA_URL_KOL = "your-dropbox-kol-url"
```

### 启动应用
```bash
streamlit run app.py
```

### 专家系统使用
1. 访问首页 `/`
2. 选择要咨询的专家
3. 输入问题（可选择上传图片）
4. 查看专家回答和总结

### 纯对话模式使用
1. 访问 `/chat`
2. 选择想要使用的模型
3. 开始对话（Gemini 模型支持图片上传）

## 目录结构
```
.
├── app.py              # 主应用（专家系统）
├── pages/
│   └── chat.py        # 纯对话模式
├── agents.py          # Agent 相关功能
├── utils.py           # 工具函数
├── requirements.txt   # 依赖列表
├── .streamlit/        # Streamlit 配置
│   ├── config.toml
│   └── secrets.toml
├── data/              # 专家资料（问答模式）
└── data_kol/          # KOL 资料
```

## 注意事项
1. 确保 API Keys 配置正确
2. 图片上传仅支持 Gemini 模型
3. 专家资料更新需要正确的 Dropbox 配置
4. 建议使用较新版本的浏览器
5. 页面刷新会保持当前的对话历史
6. 切换模型会清空对话历史

## 开发说明
- 使用 Streamlit 构建界面
- 支持 Python 3.7+
- 使用 phidata 框架处理 AI 模型
- 支持热重载开发 