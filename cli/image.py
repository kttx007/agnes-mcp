import base64, json, os, sys, tempfile, time, urllib.error, urllib.request

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com")

def _get_key():
    key = os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_API_TOKEN") or os.environ.get("APIHUB_AGNES_API_KEY")
    if not key:
        sys.exit("Error: AGNES_API_KEY not set")
    return key

def generate(prompt, mode="text2img", image_b64s=None, size="1024x768", output_dir=None, dry_run=False, api_base=None):
    base = api_base or API_BASE
    body = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    if mode in ("img2img", "compose") and image_b64s:
        body["extra_body"] = {
            "image": image_b64s,
            "response_format": "b64_json",
        }

    if dry_run:
        return {"dry_run": True, "request": body}

    req = urllib.request.Request(
        f"{base}/v1/images/generations",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code}: {e.read().decode()}")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        sys.exit(f"API request failed: {e}")
    items = resp.get("data", [])
    if not items:
        sys.exit("No images returned")

    first = items[0]
    if not first.get("url") and not first.get("b64_json"):
        sys.exit(f"Unexpected API response: {json.dumps(first)[:200]}")

    # b64_json response → decode and save
    if first.get("b64_json"):
        out = []
        for item in items:
            raw = base64.b64decode(item["b64_json"])
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                path = os.path.join(output_dir, f"agnes_img_{int(time.time() * 1000)}.png")
            else:
                os.makedirs(tempfile.gettempdir(), exist_ok=True)
                path = os.path.join(tempfile.gettempdir(), f"agnes_img_{int(time.time() * 1000)}.png")
            with open(path, "wb") as f:
                f.write(raw)
            out.append(path)
        return out

    # URL response (text2img)
    urls = [item["url"] for item in items if item.get("url")]
    if output_dir and urls:
        os.makedirs(output_dir, exist_ok=True)
        local_paths = []
        for url in urls:
            name = url.split("/")[-1].split("?")[0] or f"image_{len(local_paths)}.png"
            path = os.path.join(output_dir, name)
            urllib.request.urlretrieve(url, path)
            local_paths.append(path)
        return local_paths
    return urls

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["text2img", "img2img", "compose"])
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image-url", action="append")
    parser.add_argument("--size", default="1024x768")
    parser.add_argument("--output-dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from media import to_base64
    image_b64s = [to_base64(u) for u in args.image_url] if args.image_url else None
    result = generate(args.prompt, args.mode, image_b64s, args.size, args.output_dir, args.dry_run)
    if not args.dry_run:
        for p in result:
            print(p)
    else:
        print(json.dumps(result, indent=2))
