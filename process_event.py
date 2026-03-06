import os
import json
import requests
from github import Github, Auth

# 1. Получаем переменные окружения и проверяем, что они существуют
gh_token = os.environ.get("GITHUB_TOKEN")
gemini_key = os.environ.get("GEMINI_API_KEY")
repo_name = os.environ.get("REPOSITORY")
event_name = os.environ.get("EVENT_NAME")
raw_allowed_user = os.environ.get("ALLOWED_USER")

print("=== Запуск скрипта генерации Issue ===")

if not raw_allowed_user:
    print("❌ Ошибка: Секрет ALLOWED_USER не задан!")
    exit(1)

allowed_user = raw_allowed_user.strip().lower()

# 2. Подключаемся к GitHub
print(f"Подключение к репозиторию: {repo_name}")
auth = Auth.Token(gh_token)
gh = Github(auth=auth)
repo = gh.get_repo(repo_name)

diff_text = ""
event_context = ""
author_login = ""

# 3. Обрабатываем событие (Push или Pull Request)
print(f"Событие триггера: {event_name}")

if event_name == "push":
    commit_sha = os.environ.get("COMMIT_SHA")
    print(f"Анализируем коммит: {commit_sha}")
    commit = repo.get_commit(commit_sha)
    
    if not commit.author:
        print("⚠️ Не удалось определить автора коммита. Выход.")
        exit(0)
        
    author_login = commit.author.login.strip().lower()
    print(f"Автор: {author_login}, Разрешенный пользователь: {allowed_user}")
    
    if author_login != allowed_user:
        print("⚠️ Автор коммита не совпадает с ALLOWED_USER. Выход.")
        exit(0)
        
    event_context = f"Commit Message: {commit.commit.message}"
    
    # Собираем изменения кода
    for file in commit.files:
        diff_text += f"File: {file.filename}\nPatch:\n{file.patch}\n\n"
        if len(diff_text) > 100000:
            diff_text += "\n[Diff too large, truncated...]"
            break
            
elif event_name == "pull_request":
    pr_number = int(os.environ.get("PR_NUMBER"))
    print(f"Анализируем Pull Request: #{pr_number}")
    pr = repo.get_pull(pr_number)
    author_login = pr.user.login.strip().lower()
    
    print(f"Автор PR: {author_login}, Разрешенный пользователь: {allowed_user}")
    if author_login != allowed_user:
        print("⚠️ Автор PR не совпадает с ALLOWED_USER. Выход.")
        exit(0)
        
    event_context = f"PR Title: {pr.title}\nPR Body: {pr.body}"
    for file in pr.get_files():
        diff_text += f"File: {file.filename}\nPatch:\n{file.patch}\n\n"
        if len(diff_text) > 100000:
            diff_text += "\n[Diff too large, truncated...]"
            break
else:
    print(f"⚠️ Неизвестное событие {event_name}. Скрипт обрабатывает только push и pull_request.")
    exit(0)

print(f"Собрано {len(diff_text)} символов изменений кода.")

# 4. Подготовка промпта для нейросети
prompt = f"""
Analyze the following code changes and create a detailed description for a GitHub Issue.
IMPORTANT: The issue_title and issue_body MUST be written entirely in English.

Context:
{event_context}

Code Changes:
{diff_text}

Instructions:
1. Create a clear issue title and body explaining the changes or implementation details in English.
2. Choose the most appropriate labels from: ["bug", "documentation", "duplicate", "enhancement", "good first issue", "help wanted", "invalid", "question", "wontfix"].
3. SECURITY REVIEW: Carefully analyze the code changes for any potential security vulnerabilities (e.g., injection flaws, hardcoded secrets, XSS, insecure data handling).
   - If you find a potential vulnerability, add a section "### Security Warning" at the end of the `issue_body` describing the risk and how to fix it in English.
   - Also, if a vulnerability is found, add the label "security" to the `labels` list.

Return only a raw JSON object with no markdown formatting. The JSON must contain these exact keys:
"issue_title": string,
"issue_body": string,
"labels": list of strings
"""

# ИСПРАВЛЕНИЕ: Используем правильную версию модели
model_name = "gemini-2.0-flash" 
api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
payload = {"contents": [{"parts": [{"text": prompt}]}]}
headers = {"Content-Type": "application/json"}

print(f"Отправка запроса к Gemini API (модель: {model_name})...")

# ИСПРАВЛЕНИЕ: Добавили обработку ошибок и timeout=30 (ждать ответа не больше 30 секунд)
try:
    resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status() # Проверяем, не вернул ли сервер ошибку (например, 403 или 404)
    resp_data = resp.json()
except Exception as e:
    print(f"❌ Ошибка при обращении к API Gemini: {e}")
    print(f"Ответ сервера: {resp.text}")
    exit(1)

print("Ответ от Gemini успешно получен. Обработка текста...")

try:
    response_text = resp_data['candidates'][0]['content']['parts'][0]['text'].strip()
    
    # Очистка текста от маркдауна ```json ... ```
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
        
    if response_text.endswith("```"):
        response_text = response_text[:-3]
        
    response_text = response_text.strip()
    result = json.loads(response_text)
except Exception as e:
    print(f"❌ Ошибка при чтении JSON от Gemini: {e}")
    print(f"Что вернула нейросеть: {resp_data}")
    exit(1)

# 5. Создание Issue
if event_name == "push":
    footer = f"\n\n---\n*Generated automatically from commit {os.environ.get('COMMIT_SHA')[:7]}*"
else:
    footer = f"\n\n---\n*Generated automatically from PR #{os.environ.get('PR_NUMBER')}*"

print("Создание Issue в GitHub...")
issue = repo.create_issue(
    title=result['issue_title'],
    body=result['issue_body'] + footer,
    labels=result.get('labels', [])
)

print(f"✅ Успешно! Создано Issue #{issue.number}: {issue.title}")
