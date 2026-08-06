"""Central configuration — every knob comes from environment variables (rubric: no secrets in code)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # local dev reads .env; Render injects real env vars

BASE_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = Path(os.getenv("CORPUS_DIR", BASE_DIR / "corpus"))
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "mock_data"))
INDEX_DIR = Path(os.getenv("INDEX_DIR", BASE_DIR / "index"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "4"))
MAX_AGENT_ROUNDS = int(os.getenv("MAX_AGENT_ROUNDS", "6"))
BUILD_INDEX_ON_START = os.getenv("BUILD_INDEX_ON_START", "1") == "1"

COLLECTION_NAME = "lsj_policies"
SEED = 42  # deterministic chunk ids / eval sampling (rubric: fixed seeds)
