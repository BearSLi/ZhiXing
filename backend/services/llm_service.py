"""大模型适配层：整个应用里唯一与模型供应商打交道的地方

两个关键设计：
  1. **延迟初始化**：客户端不在 import 期创建。
     否则缺少 API Key 时整个应用起不来，而"未配置 Key"的友好提示永远执行不到
     （那是一段死代码）。现在只有真正调用 AI 时才会报错，其余功能不受影响。
  2. **供应商可替换**：换模型只改 .env 里的 BASE_URL / MODEL，业务代码零改动。
"""
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT
from errors import BizError

# 延迟初始化的单例；测试可以直接赋值替身（鸭子类型）
client = None


def get_client() -> OpenAI:
    """按需创建客户端。缺 Key 时给出可操作的提示，而不是让应用启动失败。"""
    global client
    if client is None:
        if not LLM_API_KEY:
            raise BizError(
                "未配置 LLM_API_KEY：请在 backend/.env 中填写后重启服务",
                code=503,
            )
        client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            timeout=LLM_TIMEOUT,
            max_retries=1,      # SDK 自带的有限重试：仅对超时/限流等瞬时错误生效
        )
    return client


def chat(messages: list, temperature: float = 0.3) -> str:
    """调大模型。messages=[{role, content}, ...] → 返回模型生成的文本。

    只负责"发出去、拿回来、校验非空"，权限与业务判断都在上层。
    """
    resp = get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        timeout=LLM_TIMEOUT,
    )
    content = resp.choices[0].message.content
    if content is None:
        # 模型只回了 tool_calls 或空回复时 content 会是 None；
        # 若直接返回，下游会把它塞进 JSON 变成 null，报错点会离这里很远
        raise BizError("模型未返回内容，请重试", code=502)
    return content
