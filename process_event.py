print(f"[5/6] Calling Gemini API...")
def call_gemini(prompt: str, retries: int = 4, base_delay: int = 15) -> dict:
    headers = {"Content-Type": "application/json"}
    models_to_try = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
    ]
    payload = {
        "system_instruction": {
            "parts": [{"text": "You are a professional software auditor. Always return valid JSON only. No markdown, no explanation, just the JSON object."}]
        },
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.1
        }
    }

    for model in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_api_key}"
        for attempt in range(retries):
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)

                if resp.status_code == 429:
                    wait = base_delay * (2 ** attempt)
                    print(f"[{model}] Rate limited (429). Waiting {wait}s before retry {attempt + 1}/{retries}...")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                raw = re.sub(r'^```json\s*|```$', '', raw, flags=re.MULTILINE).strip()
                
                # Добавлена защита от неверного JSON
                try:
                    result = json.loads(raw)
                    print(f"Success with model: {model}")
                    return result
                except json.JSONDecodeError:
                    print(f"[{model}] Attempt {attempt + 1} failed: Gemini returned invalid JSON. Retrying...")
                    if attempt < retries - 1:
                        time.sleep(base_delay)
                    continue

            except requests.exceptions.HTTPError as e:
                print(f"[{model}] Attempt {attempt + 1} HTTP error: {e}")
                if attempt < retries - 1:
                    time.sleep(base_delay)
            except Exception as e:
                print(f"[{model}] Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(base_delay)

        print(f"[{model}] All {retries} attempts failed, trying next model...")

    print("All models exhausted. Exiting gracefully.")
    exit(0)
