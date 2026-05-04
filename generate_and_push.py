import os
import subprocess
import sqlite3
import time
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- 1. Security, Paths, & Logging ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(BASE_DIR, "automation.log")

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

topics = ["Science", "Chemistry", "HR Trends", "Mathematics"]
date_str = datetime.utcnow().strftime('%Y-%m-%d')
human_date = datetime.utcnow().strftime('%B %d, %Y')

# --- 2. Database ---
db_path = os.path.join(BASE_DIR, "blog_admin.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, publish_date TEXT, 
                topic TEXT, post_title TEXT, model_used TEXT, status TEXT)''')
conn.commit()

# --- 3. Mermaid Sanitizer ---
def sanitize_mermaid(content):
    def clean_block(match):
        mermaid_code = match.group(1)
        mermaid_code = mermaid_code.replace('(', '').replace(')', '').replace('"', '').replace('&', 'and')
        return f"```mermaid\n{mermaid_code}\n```"
    return re.sub(r'```mermaid\n(.*?)\n```', clean_block, content, flags=re.DOTALL)

# --- 4. Prioritized Models ---
models_to_try = [
    "gemini-3-flash", 
    "gemini-3-flash-preview", 
    "gemini-2.5-flash", 
    "gemini-1.5-flash"
]

logging.info("--- Starting Production Run ---")
print(f"Starting daily generation for {len(topics)} topics...")

for selected_topic in topics:
    print(f"\n[ Processing: {selected_topic} ]")
    prompt = f"Today is {human_date}. Write a concise blog post on ACTUAL live news in {selected_topic}. Include a Mermaid diagram (graph TD/LR). No special chars in nodes. No frontmatter."
    
    status, used_model, blog_content, extracted_title = "Failed", "None", "", f"{selected_topic} Update"

    for model_name in models_to_try:
        try:
            print(f" -> Attempting generation with {model_name}...")
            logging.info(f"Trying {model_name} for {selected_topic}...")
            
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt,
                config=types.GenerateContentConfig(tools=[{"google_search": {}}])
            )
            
            raw_text = response.text
            
            # THE FIX: Strict Length Validator
            if not raw_text or len(raw_text.strip()) < 100:
                raise ValueError(f"API returned an empty or incomplete payload (Length: {len(raw_text) if raw_text else 0})")
            
            # If it passes the length check, sanitize and save
            blog_content = sanitize_mermaid(raw_text)
            used_model = model_name
            status = "Success"
            print(f" -> Success with {model_name}")
            break
            
        except Exception as e:
            error_msg = str(e).split('\n')[0] # Keep terminal output clean
            print(f" -> {model_name} failed: {error_msg}. Trying next...")
            logging.warning(f"{model_name} failed: {e}")

    # --- 5. Save if Successful ---
    if status == "Success":
        title_match = re.search(r'^#\s+(.*)', blog_content, re.MULTILINE)
        if title_match: extracted_title = title_match.group(1).strip()
        
        filename = f"content/posts/{selected_topic.lower().replace(' ', '-')}-{date_str}.md"
        os.makedirs(os.path.join(BASE_DIR, "content/posts"), exist_ok=True)
        
        frontmatter = f"---\ntitle: \"{extracted_title}\"\ndate: \"{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}Z\"\ntags: [\"{selected_topic}\"]\n---\n"
        
        with open(os.path.join(BASE_DIR, filename), "w", encoding="utf-8") as f:
            f.write(frontmatter + blog_content)

    # --- 6. Log and Sleep ---
    cursor.execute("INSERT INTO logs (publish_date, topic, post_title, model_used, status) VALUES (?, ?, ?, ?, ?)", 
                  (date_str, selected_topic, extracted_title, used_model, status))
    conn.commit()
    time.sleep(20) # Bypasses the 5 RPM Free Tier Limit

# --- 7. Generate Admin Dashboard ---
cursor.execute("SELECT publish_date, topic, post_title, model_used, status FROM logs ORDER BY id DESC LIMIT 20")
logs = cursor.fetchall()
admin_md = "---\ntitle: \"System Admin Dashboard\"\nlayout: \"admin\"\n---\n### Daily Generation Status\n| Date | Topic | Title | Model | Status |\n|---|---|---|---|---|\n"
for l in logs: 
    admin_md += f"| {l[0]} | {l[1]} | {l[2]} | `{l[3]}` | {'✅' if l[4]=='Success' else '❌'} {l[4]} |\n"
with open(os.path.join(BASE_DIR, "content/admin.md"), "w", encoding="utf-8") as f: 
    f.write(admin_md)

# --- 8. Git Push ---
try:
    subprocess.run(["git", "add", "."], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"Daily Auto-post {date_str}"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
    logging.info("Run Complete.")
    print("\n✅ All topics processed and pushed successfully.")
except subprocess.CalledProcessError as e:
    logging.error(f"Git push failed: {e}")
    print(f"\n❌ Script finished, but Git Push failed. Check your internet connection.")
