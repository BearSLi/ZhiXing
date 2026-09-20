import os
from dotenv import load_dotenv

load_dotenv()   # 读取同目录下的 .env，把变量装进环境变量

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-请更换")
TOKEN_EXPIRE_HOURS = 12