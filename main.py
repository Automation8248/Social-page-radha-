import os
import json
import time
import requests
import yt_dlp

# Directory and File Setup
METADATA_DIR = "metadata"
TITLE_FILE = os.path.join(METADATA_DIR, "title.txt")
HASHTAG_FILE = os.path.join(METADATA_DIR, "hashtag.txt")
SEARCH_FILE = os.path.join(METADATA_DIR, "search.txt") # New search keyword file

# Cooldown tracking
COOLDOWN_FILE = "history.json" 

LINK_FILE = "link.txt"
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
    """Creates necessary folders and files if they do not exist."""
    os.makedirs(METADATA_DIR, exist_ok=True)
    for file in [TITLE_FILE, HASHTAG_FILE, SEARCH_FILE, LINK_FILE, HISTORY_FILE, SAVE_FILE]:
        if not os.path.exists(file):
            open(file, 'w', encoding='utf-8').close()
            
    if not os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"titles": {}, "hashtags": {}, "searches": {}}, f)
    else:
        # Ensure 'searches' key exists for backward compatibility
        with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if "searches" not in data:
            data["searches"] = {}
            with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)

def check_history(url):
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        return url.strip() in [line.strip() for line in f.readlines()]

def update_file_record(url, file_path):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{url.strip()}\n")

def remove_from_link_txt(url_to_remove):
    with open(LINK_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(LINK_FILE, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.strip() != url_to_remove:
                f.write(line)

def get_available_metadata(filepath, item_type):
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
    with open(COOLDOWN_FILE, 'r', encoding='utf-8') as f:
        cooldowns = json.load(f)
    
    if item_type not in cooldowns:
        cooldowns[item_type] = {}
        
    cooldowns[item_type][item] = time.time()
    
    with open(COOLDOWN_FILE, 'w', encoding='utf-8') as f:
        json.dump(cooldowns, f, indent=4)

def fetch_pinterest_api(search_term):
    """Fetches a URL using the dynamic search term."""
    api_url = f"https://ansh-apis.is-dev.org/api/printrest?key=ansh&search={search_term}"
    try:
        response = requests.get(api_url)
        data = response.json()
        if isinstance(data, dict):
            return data.get('url') or data.get('video_url') or data.get('download_url')
    except Exception as e:
        print(f"API Fetch Error: {e}")
    return None

def get_headers():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def upload_to_servers(video_path):
    """Uploads the downloaded file to the first available server from the list."""
    filename = os.path.basename(video_path)
    
    servers = [
        ("Catbox", lambda: requests.post("https://catbox.moe/user/api.php", data={'reqtype': 'fileupload'}, files={'fileToUpload': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Litterbox", lambda: requests.post("https://litterbox.catbox.moe/resources/internals/api.php", data={'reqtype': 'fileupload', 'time': '72h'}, files={'fileToUpload': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("0x0.st", lambda: requests.post("https://0x0.st", files={'file': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Uguu", lambda: requests.post("https://uguu.se/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("qu.ax", lambda: requests.post("https://qu.ax/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Pixeldrain", lambda: requests.post("https://pixeldrain.com/api/file", files={'file': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Fileditch", lambda: requests.post("https://up1.fileditch.com/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("Oshi.at", lambda: requests.post("https://oshi.at", files={'f': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("FilePort", lambda: requests.post("https://fileport.io/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=60)),
        ("FileShot", lambda: requests.post("https://fileshot.net/upload.php", files={'files[]': open(video_path, 'rb')}, headers=get_headers(), timeout=60))
    ]

    for name, req_func in servers:
        try:
            print(f"Uploading to {name}...")
            response = req_func()
            if response.status_code in [200, 201]:
                # Dynamic parsing based on server response types
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
            print(f"❌ {name} failed or returned unreadable format.")
        except Exception as e:
            print(f"❌ Error with {name}: {e}")
            
    return None

def send_to_webhook(title, hashtag, uploaded_url):
    """Sends the newly generated server URL to the webhook."""
    if not WEBHOOK_URL:
        return False
    payload = {"title": title, "hashtag": hashtag, "video_url": uploaded_url}
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Webhook error: {e}")
        return False

def send_telegram_message(token, text):
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
    
    if not title or not hashtag:
        msg = "⚠️ **Automation Failed**\nAll titles/hashtags are currently on a 30-day cooldown."
        send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
        return

    # 1. Determine Source URL
    target_url = None
    is_from_link_txt = False
    
    with open(LINK_FILE, 'r', encoding='utf-8') as f:
        links = [line.strip() for line in f.readlines() if line.strip()]
        
    for link in links:
        if not check_history(link):
            target_url = link
            is_from_link_txt = True
            break
            
    if not target_url:
        if not search_term:
            msg = "⚠️ **Automation Failed**\n`link.txt` is empty and no valid search keywords are off cooldown in `search.txt`."
            send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
            return
            
        print(f"link.txt exhausted. Fetching from API using keyword: '{search_term}'...")
        api_url = fetch_pinterest_api(search_term)
        if api_url and not check_history(api_url):
            target_url = api_url

    if not target_url:
        msg = "⚠️ **Automation Failed**\nNo valid source URL found to process."
        send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
        return
        
    # 2. Download the Media
    video_path = "video.mp4"
    try:
        ydl_opts = {'outtmpl': video_path, 'format': 'best', 'merge_output_format': 'mp4'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
            
        # 3. Upload to Fallback Servers
        uploaded_direct_url = upload_to_servers(video_path)
        
        if not uploaded_direct_url:
            msg = f"❌ **Automation Failed**\nAll upload servers failed for original URL: {target_url}"
            send_telegram_message(TELEGRAM_TOKEN_FAIL, msg)
            return
            
        # 4. Send to Webhook
        success = send_to_webhook(title, hashtag, uploaded_direct_url)
        
        if success:
            # Update cooldowns
            update_cooldown(title, "titles")
            update_cooldown(hashtag, "hashtags")
            if not is_from_link_txt and search_term:
                update_cooldown(search_term, "searches")
                
            update_file_record(target_url, HISTORY_FILE)
            update_file_record(target_url, SAVE_FILE)
            
            if is_from_link_txt:
                remove_from_link_txt(target_url)
                
            success_msg = (
                f"🚀 **Automation: Webhook Poster**\n"
                f"📝 **Title:** {title}\n"
                f"🏷️ **Hashtags:** {hashtag}\n"
                f"📥 **Source URL:** {target_url}\n"
                f"🔗 **Uploaded URL:** {uploaded_direct_url}\n"
                f"✅ **Status:** Delivered to Webhook!"
            )
            send_telegram_message(TELEGRAM_TOKEN_SUCCESS, success_msg)
        else:
            fail_msg = f"❌ **Automation Failed**\nFailed to post payload to Webhook."
            send_telegram_message(TELEGRAM_TOKEN_FAIL, fail_msg)
            
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

if __name__ == "__main__":
    main()
