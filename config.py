import logging
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (если есть)
load_dotenv()

# --- Configuration ---
PLATFORM_API_BASE_URL = os.getenv("PLATFORM_API_BASE_URL", "http://10.9.0.160:9076")
PLATFORM_API_TOKEN = os.getenv("PLATFORM_API_TOKEN", "YW1vbDpDMG0xbmR3NHIzUGxAdGYwcm0=")
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:32b")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)  # Раскомментировать для отладки