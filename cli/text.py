import json, os, sys, urllib.request

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com")

def _get_key():
    key = os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_API_TOKEN") or os.environ.get("APIHUB_AGNES_API_KEY")
    if not key:
        sys.exit("Error: AGNES_API_KEY not set. Run 'agnes setup' or export it.")
    return key

def _headers():
    return {"Authorization": f"Bearer {_get_key()}",
        "Content-Type": "application/json"
    }

def chat(prompt, system=None, messages=None, stream=False, temperature=0.7, top_p=0.9, max_tokens=4096, tools_json=None, tool_choice=None, json_output=False, dry_run=False, api_base=None, image_b64s=None, timeout=120):
    base = api_base or API_BASE
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    if image_b64s:
        content = []
        for b64 in image_b64s:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        content.append({"type": "text", "text": prompt or ""})
        msgs.append({"role": "user", "content": content})
    elif messages:
        for m in messages:
            role, content = m.split(":", 1)
            msgs.append({"role": role.strip(), "content": content.strip()})
    else:
        msgs.append({"role": "user", "content": prompt})

    body = {
        "model": "agnes-2.0-flash",
        "messages": msgs,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": stream
    }
    if tools_json:
        body["tools"] = json.loads(tools_json) if isinstance(tools_json, str) else tools_json
    if tool_choice:
        body["tool_choice"] = tool_choice

    if dry_run:
        return {"dry_run": True, "request": body}

    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers=_headers(),
        method="POST"
    )

    if stream:
        return _stream_chat(req, timeout)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
    except Exception as e:
        sys.exit(f"API request failed: {e}")
    choice = data["choices"][0]
    result = {"content": choice["message"].get("content", ""), "finish_reason": choice["finish_reason"]}
    if json_output:
        return result
    print(result["content"])

def _stream_chat(req, timeout=120):
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        sys.exit(f"Stream request failed: {e}")
    buffer = ""
    full_content = ""
    for chunk in resp:
        buffer += chunk.decode()
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if not data.get("choices"):
                        continue
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    full_content += content
                    print(content, end="", flush=True)
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
    print()
    return full_content

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--system")
    parser.add_argument("--message", action="append")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--tools-json")
    parser.add_argument("--tool-choice")
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = chat(args.prompt, args.system, args.message, args.stream, args.temperature, args.top_p, args.max_tokens, args.tools_json, args.tool_choice, args.json_output, args.dry_run)
    if isinstance(result, dict):
        print(json.dumps(result, indent=2))
