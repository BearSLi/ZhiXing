from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from services.ticket_service import BizError

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def chat(messages: list, temperature: float = 0.3) -> str:
    if not LLM_API_KEY:
        raise BizError("未配置 LLM_API_KEY（检查 backend/.env 并重启服务）", code=500) 
    try:
        resp = client.chat.completions.create(
            model = LLM_MODEL,
            messages = messages,
            temperature = temperature,
            timeout = 30, 
        )
        return resp.choices[0].message.content
    except Exception:
        raise
