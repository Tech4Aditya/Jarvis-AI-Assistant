import json

MEMORY_FILE = "memory.json"

def save_memory(user, bot):
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
    except:
        data = []

    data.append({"user": user, "bot": bot})

    with open(MEMORY_FILE, "w") as f:
        json.dump(data[-10:], f)  # last 10 only


def get_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return []