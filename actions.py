import subprocess
import webbrowser
import requests
import os

NEWS_KEY = os.getenv("NEWS_API_KEY")

def get_news():
    url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_KEY}"
    res = requests.get(url).json()

    articles = res.get("articles", [])[:5]
    return "\n".join([a["title"] for a in articles])


def perform_action(cmd):
    cmd = cmd.lower()

    apps = {
        "chrome": "start chrome",
        "notepad": "notepad",
        "calculator": "calc",
        "explorer": "explorer",
        "task manager": "taskmgr",
        "cmd": "start cmd",
        "vscode": "code"
    }

    for key in apps:
        if key in cmd:
            subprocess.Popen(apps[key], shell=True)
            return f"Opening {key}"

    if "youtube" in cmd:
        webbrowser.open("https://youtube.com")
        return "Opening YouTube"

    if "google" in cmd:
        webbrowser.open("https://google.com")
        return "Opening Google"

    if "news" in cmd:
        return get_news()

    return None