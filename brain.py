import os
from groq import Groq
from dotenv import load_dotenv

"""
brain.py — On-device AI reasoning via Ollama.
Replaces the old cloud-based Groq client. All inference runs locally
against a model pulled with ollama pull <MODEL>.
"""

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b" # swap for qwen2.5:0.5b or smollm2 if this is too slow on your hardware

SYSTEM_PROMPT = {
"role": "system",
"content": "You are JARVIS, a concise, helpful local AI assistant. Keep answers short unless asked for detail."
}

chat_history = [SYSTEM_PROMPT]

def ask_ai(prompt: str) -> str:
chat_history.append({"role": "user", "content": prompt})

try:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": chat_history[-11:],  # system + last 10 turns
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
except requests.exceptions.ConnectionError:
    return (
        "I can't reach the local Ollama server. "
        "Make sure it's running: `ollama serve`."
    )
except requests.exceptions.RequestException as e:
    return f"Local model call failed: {e}"

reply = response.json()["message"]["content"]
chat_history.append({"role": "assistant", "content": reply})

return reply
def reset_history():
global chat_history
chat_history = [SYSTEM_PROMPT]