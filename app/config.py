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
MODEL = os.getenv("MODEL", "openai/gpt-oss-120b")  # Groq removed all Llama chat models mid-project; swapped 2026-08 (fallback: openai/gpt-oss-20b)
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "4"))
# Eval-ablation override: when set (>0), retrieval uses THIS k even if the model passes k explicitly
# (the MCP tool schema defaults k=4, so RETRIEVAL_K alone can't drive the k=2/4/8 ablation). 0 = off.
FORCE_RETRIEVAL_K = int(os.getenv("FORCE_RETRIEVAL_K", "0"))
MAX_AGENT_ROUNDS = int(os.getenv("MAX_AGENT_ROUNDS", "8"))  # gpt-oss-120b explores more thoroughly than llama did
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")  # gpt-oss models: low cuts multi-round latency ~5x; quality comes from grounding, not private deliberation
BUILD_INDEX_ON_START = os.getenv("BUILD_INDEX_ON_START", "1") == "1"

COLLECTION_NAME = "lsj_policies"
SEED = 42  # deterministic chunk ids / eval sampling (rubric: fixed seeds)
