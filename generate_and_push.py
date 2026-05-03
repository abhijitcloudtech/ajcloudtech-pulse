import os
import subprocess
import sqlite3
from datetime import datetime
import google.generativeai as genai

# --- Configuration ---
GITHUB_REPO_PATH = "/home/ubuntu/ajcloudtech-pulse" # Update path if needed
GEMINI_API_KEY = "YOUR_API_KEY_HERE"
genai.configure(api_key=GEMINI_API_KEY)

# Daily Topic Selection
topics = ["Science", "Chemistry", "HR Trends", "Mathematics"]
day_of_year = datetime.now().timetuple().tm_yday
selected_topic = topics[day_of_year % len(topics)]
date_str = datetime.now().strftime('%Y-%m-%d')
human_date = datetime.now().strftime('%B %d, %Y')

# --- 1. Database Setup ---
db_path = os.path.join(GITHUB_REPO_PATH, "blog_admin.db")
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

# --- 2. Model Fallback Logic ---
# Note: Ensure these exact string names match Google's active API endpoints
models_to_try = [
    "gemini-3-flash", 
    "gemini-2.5-flash", 
    "gemini-3.1-flash-lite", 
    "gemini-2.5-flash-lite"
]

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
        print(f"Attempting generation with {model_name}...")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        blog_content = response.text
        used_model = model_name
        status = "Success"
        break # Exit loop if successful
    except Exception as e:
        print(f"{model_name} failed: {e}. Falling back to next model...")

# --- 3. Save Blog Post (If Success) ---
if status == "Success":
    filename = f"content/posts/{selected_topic.lower().replace(' ', '-')}-{date_str}.md"
    full_path = os.path.join(GITHUB_REPO_PATH, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    frontmatter = f"""---
title: "{selected_topic} Daily Update: {human_date}"
date: "{datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')}Z"
draft: false
tags: ["{selected_topic}"]
---
"""
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + blog_content)

# --- 4. Log to Database ---
cursor.execute("INSERT INTO logs (publish_date, topic, model_used, status) VALUES (?, ?, ?, ?)", 
               (date_str, selected_topic, used_model, status))
conn.commit()

# --- 5. Generate Admin Dashboard Page ---
# Fetch the last 10 logs
cursor.execute("SELECT publish_date, topic, model_used, status FROM logs ORDER BY id DESC LIMIT 10")
recent_logs = cursor.fetchall()

admin_md = f"""---
title: "System Admin Dashboard"
date: "{datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')}Z"
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

admin_path = os.path.join(GITHUB_REPO_PATH, "content/admin.md")
with open(admin_path, "w", encoding="utf-8") as f:
    f.write(admin_md)

conn.close()

# --- 6. Git Push ---
os.chdir(GITHUB_REPO_PATH)
subprocess.run(["git", "add", "."]) # Add both the post, the admin page, and the db
subprocess.run(["git", "commit", "-m", f"Auto-post: {selected_topic} & Admin Update"])
subprocess.run(["git", "push", "origin", "main"])

print(f"Process complete. Final Status: {status}")
