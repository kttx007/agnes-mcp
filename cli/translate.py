import json, os, sys, urllib.error, urllib.request

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com")

def _get_key():
    return os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_API_TOKEN") or os.environ.get("APIHUB_AGNES_API_KEY")

def needs_translation(text):
    return any(ord(c) > 127 for c in text)

def translate(prompt, api_base=None):
    """Translate non-English prompt to English using agnes-2.0-flash."""
    if not needs_translation(prompt):
        return prompt
    base = api_base or API_BASE
    key = _get_key()
    if not key:
        return prompt
    body = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": "Translate the following prompt to English. Preserve all visual details, style, lighting, composition, and quality terms. Return ONLY the translated text, no explanation."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1024
    }
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code}: {e.read().decode()}")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        sys.exit(f"API request failed: {e}")
    return resp["choices"][0]["message"]["content"]

if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    print(translate(text))
