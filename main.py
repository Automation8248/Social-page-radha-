import os
import json
import time
import requests
import yt_dlp

# Directory and File Setup
METADATA_DIR = "metadata"
TITLE_FILE = os.path.join(METADATA_DIR, "title.txt")
HASHTAG_FILE = os.path.join(METADATA_DIR, "hashtag.txt")
SEARCH_FILE = os.path.join(METADATA_DIR, "search.txt") 

# Cooldown and Tracking Files
COOLDOWN_FILE = "history.json" 
HISTORY_FILE = "history.txt"
SAVE_FILE = "save.txt"

# 30 Days Cooling Time in Seconds
COOLDOWN_SECONDS = 30 * 24 * 60 * 60

# Tokens & Webhook setup
TELEGRAM_TOKEN_SUCCESS = os.environ.get("TELEGRAM_TOKEN_SUCCESS")
TELEGRAM_TOKEN_FAIL = os.environ.get("TELEGRAM_TOKEN_FAIL")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

def init_files():
    """Initializes required files and handles corrupt JSON automatically."""
    os.makedirs(METADATA_DIR, exist_ok=True)
    for file in [TITLE_FILE, HASHTAG_FILE, SEARCH_FILE, HISTORY_FILE, SAVE_FILE]:
        if not os.path.exists(file):
            open(file, 'w', encoding='utf-8').close()
            
    # Safely initialize or reset history.json
    if not os.path.exists(COOLDOWN_FILE) or os.path.getsize(COOLDOWN_FILE) == 0:
        with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"titles": {}, "hashtags": {}, "searches": {}}, f)
    else:
        try:
            with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
                json.load(f)
        except json.JSONDecodeError:
            with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
                json.dump({"titles": {}, "hashtags": {}, "searches": {}}, f)

def check_history(url):
    """Strictly ensures the exact URL does not exist in history.txt."""
    if not os.path.exists(HISTORY_FILE):
        return False
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        history_urls = set(line.strip() for line in f.readlines() if line.strip())
    return url.strip() in history_urls

def update_file_record(url, file_path):
    """Appends the URL to history tracking logs."""
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{url.strip()}\n")

def get_available_metadata(filepath, item_type):
    """Fetches titles/hashtags/searches respecting the 30-day cooldown."""
    with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
        cooldowns = json.load(f)
    
    current_time = time.time()
    item_cooldowns = cooldowns.get(item_type, {})

    with open(filepath, 'r', encoding='utf-8') as f:
        items = [line.strip() for line in f.readlines() if line.strip()]

    for item in items:
        last_used = item_cooldowns.get(item, 0)
        if current_time - last_used > COOLDOWN_SECONDS:
            return item
    return None

def update_cooldown(item, item_type):
    """Records the timestamp of the used metadata into history.json."""
    with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
        cooldowns = json.load(f)
    
    if item_type not in cooldowns:
        cooldowns[item_type] = {}
        
    cooldowns[item_type][item] = time.time()
    
    with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
        json.dump(cooldowns, f, indent=4)

def fetch_pinterest_api(search_term):
    """Fetches API and extracts the first unused media URL."""
    api_url = f"https://ansh-apis.is-dev.org/api/printrest?key=ansh&search={search_term}"
    try:
        response = requests.get(api_url)
        data = response.json()
        
        pins = data.get("data", {}).get("pins", [])
        
        for pin in pins:
            media_url = None
            
            # Extract Image URL
            if pin.get("media_type") == "image":
                images = pin.get("images", {})
                media_url = images.get("orig", {}).get("url") or images.get("736x", {}).get("url")
            
            # Extract Video URL
            elif pin.get("media_type") == "video":
                formats = pin.get("video", {}).get("formats", [])
                if formats:
                    media_url = formats[0].get("url")
                    
            # Check history before returning
            if media_url and media_url.startswith("http"):
                if not check_history(media_url):
                    return media_url
                    
    except Exception as e:
        print(f"API Fetch Error: {e}")
    return None

def get_headers():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def upload_to_servers(file_path):
    """Uploads the local file to multiple fallback servers sequentially."""
    filename = os.path.basename(file_path)
    servers = [
        ("Catbox", lambda: requests.post("https://catbox.moe/user/api.php", data={'reqtype': 'fileupload'}, files={'fileToUpload': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Litterbox", lambda: requests.post("https://litterbox.catbox.moe/resources/internals/api.php", data={'reqtype': 'fileupload', 'time': '72h'}, files={'fileToUpload': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("0x0.st", lambda: requests.post("https://0x0.st", files={'file': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Uguu", lambda: requests.post("https://uguu.se/upload.php", files={'files[]': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("qu.ax", lambda: requests.post("https://qu.ax/upload.php", files={'files[]': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Pixeldrain", lambda: requests.post("https://pixeldrain.com/api/file", files={'file': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Fileditch", lambda: requests.post("https://up1.fileditch.com/upload.php", files={'files[]': open(file_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Oshi.at", lambda: requests.post("https://oshi.at", files={'f': open(file_path, 'rb')}, headers=get_headers(), timeout=60))
    ]

    for name, req_func in servers:
        try:
            print(f"Uploading to {name}...")
            response = req_func()
            if response.status_code in [200, 201]:
                try:
                    data = response.json()
                    if name == "Pixeldrain":
                        return f"https://pixeldrain.com/api/file/{data.get('id')}"
                    elif "files" in data and len(data["files"]) > 0:
                        return data["files"][0].get("url")
                    elif "url" in data:
                        return data["url"]
                except ValueError:
                    text = response.text.strip()
                    if text.startswith("http"):
                        return text
            print(f"❌ {name} failed.")
        except Exception as e:
            print(f"❌ Error with {name}: {e}")
            
    return None

def send_to_webhook(title, hashtag, uploaded_url):
    """Sends JSON payload to the Webhook URL."""
    if not WEBHOOK_URL:
        return False
    payload = {"title": title, "hashtag": hashtag, "media_url": uploaded_url}
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Webhook error: {e}")
        return False

def send_telegram_message(token, text):
    """Sends execution alerts to Telegram."""
    if not token or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def main():
    init_files()
    
    title = get_available_metadata(TITLE_FILE, "titles")
    hashtag = get_available_metadata(HASHTAG_FILE, "hashtags")
    search_term = get_available_metadata(SEARCH_FILE, "searches")
    
    if not title or not hashtag or not search_term:
        msg = "⚠️ **Automation Failed**\nTitles, hashtags, or search keywords are currently exhausted (30-day cooldown)."
        send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
        return

    print(f"Fetching from API using keyword: '{search_term}'...")
    target_url = fetch_pinterest_api(search_term)

    if not target_url:
        msg = f"⚠️ **Automation Failed**\nNo valid or fresh media URL found for search term: '{search_term}'. All available media might be in history.txt."
        send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
        return
        
    media_path_base = "media_download"
    final_path = ""
    
    try:
        # Bypass yt-dlp for direct image links
        if target_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            ext = target_url.split(".")[-1]
            final_path = f"{media_path_base}.{ext}"
            img_data = requests.get(target_url).content
            with open(final_path, 'wb') as handler:
                handler.write(img_data)
        else:
            # Use yt-dlp for video files
            ydl_opts = {'outtmpl': media_path_base, 'format': 'best', 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                ext = info.get('ext', 'mp4')
                final_path = f"{media_path_base}.{ext}"
                os.rename(media_path_base, final_path)
            
        uploaded_direct_url = upload_to_servers(final_path)
        
        if not uploaded_direct_url:
            msg = f"❌ **Automation Failed**\nAll upload servers failed for original URL: {target_url}"
            send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
            return
            
        success = send_to_webhook(title, hashtag, uploaded_direct_url)
        
        if success:
            # Update cooldown limits
            update_cooldown(title, "titles")
            update_cooldown(hashtag, "hashtags")
            update_cooldown(search_term, "searches")
            
            # Permanently block the original media URL from being reused
            update_file_record(target_url, HISTORY_FILE)
            update_file_record(target_url, SAVE_FILE)
                
            success_msg = (
                f"🚀 **Automation: Webhook Poster**\n"
                f"📝 **Title:** {title}\n"
                f"🏷️ **Hashtags:** {hashtag}\n"
                f"📥 **API Keyword:** {search_term}\n"
                f"🔗 **Uploaded URL:** {uploaded_direct_url}\n"
                f"✅ **Status:** Delivered to Webhook!"
            )
            send_telegram_message(TELEGRAM_TOKEN_SUCCESS, success_msg)
        else:
            fail_msg = f"❌ **Automation Failed**\nFailed to post payload to Webhook."
            send_telegram_message(TELEGRAM_TOKEN_FAIL, fail_msg)
            
    finally:
        # Safely cleanup downloaded artifacts
        for f in os.listdir("."):
            if f.startswith(media_path_base):
                os.remove(f)

if __name__ == "__main__":
    main()
