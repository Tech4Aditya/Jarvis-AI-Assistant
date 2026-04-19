import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

chat_history = []

def ask_ai(prompt):
    chat_history.append({"role": "user", "content": prompt})

    chat = client.chat.completions.create(
        messages=chat_history[-10:],  # limit memory
        model="openai/gpt-oss-120b"
    )

    reply = chat.choices[0].message.content
    chat_history.append({"role": "assistant", "content": reply})

    return reply