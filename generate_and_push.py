import os
import subprocess
from datetime import datetime
import google.generativeai as genai

# Configuration
GITHUB_REPO_PATH = "/home/ubuntu/ajcloudtech-pulse" # Update with your actual path
GEMINI_API_KEY = "AIzaSyBkt8lpG-XnywVl_ijqaKit4-rxZ1LLBIY"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

topics = ["Science", "Chemistry", "HR Trends", "Mathematics"]
day_of_year = datetime.now().timetuple().tm_yday
selected_topic = topics[day_of_year % len(topics)]

prompt = f"""
Write a fresh, insightful, and concise blog post based on recent market or news trends in the field of {selected_topic}.
Include the title, date, and body formatted in Markdown. 
CRITICAL REQUIREMENT: You MUST include at least one high-level flow diagram, process chart, or architectural diagram illustrating a core concept from the article. The diagram MUST be written using Mermaid.js syntax inside a ```mermaid code block.
Do not include frontmatter, just the content.
"""

response = model.generate_content(prompt)

# Prepare file paths
date_str = datetime.now().strftime('%Y-%m-%d')
filename = f"content/posts/{selected_topic.lower().replace(' ', '-')}-{date_str}.md"
full_path = os.path.join(GITHUB_REPO_PATH, filename)
os.makedirs(os.path.dirname(full_path), exist_ok=True)

# Generate Frontmatter
frontmatter = f"""---
title: "{selected_topic} Daily Update: {datetime.now().strftime('%B %d, %Y')}"
date: "{datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')}Z"
draft: false
tags: ["{selected_topic}"]
---
"""

# Write to file
with open(full_path, "w", encoding="utf-8") as f:
    f.write(frontmatter + response.text)

# Git Commit and Push
os.chdir(GITHUB_REPO_PATH)
subprocess.run(["git", "add", filename])
subprocess.run(["git", "commit", "-m", f"Auto-post: {selected_topic} - {date_str}"])
subprocess.run(["git", "push", "origin", "main"])

print(f"Successfully generated and pushed {filename}")
