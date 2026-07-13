# JARVIS — Local AI Desktop Assistant

A desktop assistant with a PyQt6 chat UI where the core AI reasoning runs
**entirely on-device** via [Ollama](https://ollama.com), with no cloud LLM
calls required.

## Problem

Most "AI assistant" projects ship API keys and route every message to a
cloud LLM — no privacy, no offline use, and a running cost per user.

## Solution

JARVIS routes commands through a small rule-based action layer first
(open apps, open sites), and falls back to a **local** quantized LLM for
everything else. Nothing you type is sent off your machine unless you
explicitly ask for the news headlines (a clearly separated cloud support
feature).

## On-Device AI Usage

- **Model:** `qwen2.5:3b` (Qwen2.5, 3B parameters)
- **Source:** [Ollama model library](https://ollama.com/library/qwen2.5)
- **License:** Apache 2.0 (Qwen2.5)
- **Format / runtime:** GGUF, served locally by Ollama on `localhost:11434`
- **Footprint:** ~1.9 GB on disk
- **What's local:** all chat reasoning, response generation, and
  text-to-speech (`pyttsx3`, OS-native voices, offline)
- **What's cloud (optional, non-core):** the `news` command, which hits
  NewsAPI for headlines — everything else works with no internet connection

To use a lighter model on weaker hardware, swap `MODEL` in `brain.py` for
`qwen2.5:0.5b` or `smollm2`.

## Tech Stack

- PyQt6 + QWebEngineView (chat UI, `ui.html` + `ui_qt.py`)
- Ollama (local LLM serving)
- `requests` (HTTP calls to local Ollama server)
- `pyttsx3` (offline text-to-speech)
- Plain JSON file (`memory.json`) for local conversation history

## Setup

```bash
# 1. Install Ollama: https://ollama.com/download
ollama pull qwen2.5:3b
ollama serve          # leave running in a separate terminal

# 2. Install Python deps
pip install -r requirements.txt

# 3. (optional) copy .env.example to .env and add NEWS_API_KEY

# 4. Run
python main.py
```

## Usage

Type a command into the input box:
- `open chrome`, `open notepad`, `open calculator` — launches local apps
- `open youtube`, `open google` — opens in default browser
- `news` — fetches top headlines (requires `NEWS_API_KEY`)
- anything else — answered by the local LLM

## Known Limitations / Future Scope

- Voice input (speech-to-text) isn't wired up yet — mic button is a stub
- No streaming token-by-token output yet (response arrives as one block)
- Memory is a flat last-10-exchanges JSON file, not embeddings-based recall

## License

MIT — see `LICENSE`.
