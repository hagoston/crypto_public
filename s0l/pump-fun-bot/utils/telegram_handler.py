import requests
import os
from dotenv import load_dotenv

load_dotenv()

MESSAGE = "Hello from Python with uv 🎉"

def send_telegram_message(text: str, token: str = os.getenv("BOT_TOKEN"), chat_id: str = os.getenv("CHAT_ID")):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, data=payload)
    return response.json()

def get_telegram_updates(token: str = os.getenv("BOT_TOKEN"), offset: int = None):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": offset, "timeout": 60}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching telegram updates: {e}")
        return None

if __name__ == "__main__":
    result = send_telegram_message(MESSAGE)
    print(result)
