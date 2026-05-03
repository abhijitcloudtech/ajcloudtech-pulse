import os
import subprocess
import sqlite3
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- 1. Security & Configuration ---
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please ensure your .env file is set up correctly.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
client = genai.Client(api_key=GEMINI_API_KEY)

# Topic Setup
topics = ["Science", "Chemistry", "HR Trends", "Mathematics"]
date_str = datetime.utcnow().strftime('%Y-%m-%d')
human_date = datetime.utcnow().strftime('%B %d, %Y')

# --- 2. Database Setup & Auto-Upgrade ---
db_path = os.path.join(BASE_DIR, "blog_admin.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        publish_date TEXT,
        topic TEXT,
        model_used TEXT,
        status TEXT
    )
''')

# Upgrade table if 'post_title' doesn't exist
cursor.execute("PRAGMA table_info(logs)")
columns = [col[1] for col in cursor.fetchall()]
if "post_title" not in columns:
    cursor.execute("ALTER TABLE logs ADD COLUMN post_title TEXT DEFAULT 'Untitled'")
    
conn.commit()

# --- 3. Model Configuration ---
models_to_try = [
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite"
]

print(f"Starting daily generation for {len(topics)} topics...")

# --- 4. The Core Generation Loop ---
for selected_topic in topics:
    print(f"\n[ Processing: {selected_topic} ]")
    
    prompt = f"""
    Today is {human_date}. 
    Write a fresh, insightful, and concise blog post based on ACTUAL live market news and trends from this week in the field of {selected_topic}. 
    Do not use examples or dates from 2023 or 2024. Focus strictly on current, real-time developments.
    
    Include the title, today's date, and body formatted in Markdown. 
    
    CRITICAL REQUIREMENT: You MUST include at least one high-level flow diagram (graph TD or LR) illustrating a core concept from the article. 
    The diagram MUST be written using Mermaid.js syntax inside a ```mermaid code block.
    MERMAID RULES: Keep it incredibly simple. Do NOT use parentheses (), quotes "", ampersands &, or special characters inside the node names. Use standard A[Text] --> B[Text] formatting only.
    
    Do not include frontmatter, just the content.
    """

    blog_content = ""
    used_model = "None"
    status = "Failed - Exhausted Limits"
    extracted_title = f"{selected_topic} Update"

    for model_name in models_to_try:
        try:
            print(f" -> Attempting generation with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                # Force the AI to search the live internet
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            blog_content = response.text
            used_model = model_name
            status = "Success"
            print(f" -> Success with {model_name}")
            break  
        except Exception as e:
            print(f" -> {model_name} failed: {e}. Trying next...")

    # --- 5. Save Blog Post & Extract Title (If Success) ---
    if status == "Success":
        # Extract the first H1 tag (# Title)
        title_match = re.search(r'^#\s+(.*)', blog_content, re.MULTILINE)
        if title_match:
            extracted_title = title_match.group(1).strip()

        filename = f"content/posts/{selected_topic.lower().replace(' ', '-')}-{date_str}.md"
        full_path = os.path.join(BASE_DIR, filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        frontmatter = f"""---
title: "{selected_topic} Daily Update: {human_date}"
date: "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}Z"
draft: false
tags: ["{selected_topic}"]
---
"""
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + blog_content)

    # --- 6. Log to Database ---
    cursor.execute("INSERT INTO logs (publish_date, topic, post_title, model_used, status) VALUES (?, ?, ?, ?, ?)", 
                   (date_str, selected_topic, extracted_title, used_model, status))
    conn.commit()
    
    # Sleep to prevent hitting free-tier API rate limits
    time.sleep(5) 

# --- 7. Generate Admin Dashboard Page ---
cursor.execute("SELECT publish_date, topic, post_title, model_used, status FROM logs ORDER BY id DESC LIMIT 20")
recent_logs = cursor.fetchall()

admin_md = f"""---
title: "System Admin Dashboard"
date: "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}Z"
draft: false
type: "page"
layout: "admin"
---

### Daily Generation Status

| Date | Topic | Title | Model Used | Status |
|------|-------|-------|------------|--------|
"""
for log in recent_logs:
    status_icon = "✅" if log[4] == "Success" else "❌"
    # log[0]=date, log[1]=topic, log[2]=title, log[3]=model, log[4]=status
    admin_md += f"| {log[0]} | {log[1]} | {log[2]} | `{log[3]}` | {status_icon} {log[4]} |\n"

admin_path = os.path.join(BASE_DIR, "content/admin.md")
with open(admin_path, "w", encoding="utf-8") as f:
    f.write(admin_md)

conn.close()

# --- 8. Git Push ---
os.chdir(BASE_DIR)
subprocess.run(["git", "add", "."])
subprocess.run(["git", "commit", "-m", f"Auto-post: Daily topics and Admin log for {date_str}"])
subprocess.run(["git", "push", "origin", "main"])

print("\nAll topics processed and pushed successfully.")
