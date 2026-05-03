import os
import subprocess
import sqlite3
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai

# --- 1. Security & Configuration ---
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Future Phase 2 Setup ---
# In Phase 2, we will replace this hardcoded list by fetching from the SQLite DB.
topics = ["Science", "Chemistry", "HR Trends", "Mathematics"]
date_str = datetime.utcnow().strftime('%Y-%m-%d')
human_date = datetime.utcnow().strftime('%B %d, %Y')

# --- 2. Database Setup ---
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
conn.commit()

models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

print(f"Starting daily generation for {len(topics)} topics...")

# --- 3. The Core Generation Loop ---
for selected_topic in topics:
    print(f"\n[ Processing: {selected_topic} ]")
    
    prompt = f"""
    Write a fresh, insightful, and concise blog post based on recent market or news trends in the field of {selected_topic}.
    Include the title, date, and body formatted in Markdown. 
    CRITICAL REQUIREMENT: You MUST include at least one high-level flow diagram, process chart, or architectural diagram illustrating a core concept from the article. The diagram MUST be written using Mermaid.js syntax inside a ```mermaid code block.
    Do not include frontmatter, just the content.
    """

    blog_content = ""
    used_model = "None"
    status = "Failed - Exhausted Limits"

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            blog_content = response.text
            used_model = model_name
            status = "Success"
            print(f" -> Success with {model_name}")
            break  
        except Exception as e:
            print(f" -> {model_name} failed: {e}. Trying next...")

    # Save Blog Post (If Success)
    if status == "Success":
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

    # Log to Database
    cursor.execute("INSERT INTO logs (publish_date, topic, model_used, status) VALUES (?, ?, ?, ?)", 
                   (date_str, selected_topic, used_model, status))
    conn.commit()
    
    # Sleep to prevent hitting free-tier API rate limits
    time.sleep(5) 

# --- 4. Generate Admin Dashboard Page ---
# Fetch the last 20 logs so you can see multiple days of the 4 topics
cursor.execute("SELECT publish_date, topic, model_used, status FROM logs ORDER BY id DESC LIMIT 20")
recent_logs = cursor.fetchall()

admin_md = f"""---
title: "System Admin Dashboard"
date: "{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}Z"
draft: false
type: "page"
layout: "admin"
---

### Daily Generation Status

| Date | Topic | Model Used | Status |
|------|-------|------------|--------|
"""
for log in recent_logs:
    status_icon = "✅" if log[3] == "Success" else "❌"
    admin_md += f"| {log[0]} | {log[1]} | `{log[2]}` | {status_icon} {log[3]} |\n"

admin_path = os.path.join(BASE_DIR, "content/admin.md")
with open(admin_path, "w", encoding="utf-8") as f:
    f.write(admin_md)

conn.close()

# --- 5. Git Push ---
os.chdir(BASE_DIR)
subprocess.run(["git", "add", "."])
subprocess.run(["git", "commit", "-m", f"Auto-post: All Topics for {date_str}"])
subprocess.run(["git", "push", "origin", "main"])

print("\nAll topics processed and pushed successfully.")
