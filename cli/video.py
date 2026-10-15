import json, os, sys, time, urllib.error, urllib.parse, urllib.request

API_BASE = os.environ.get("AGNES_API_BASE", "https://apihub.agnes-ai.com")

def _get_key():
    key = os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_API_TOKEN") or os.environ.get("APIHUB_AGNES_API_KEY")
    if not key:
        sys.exit("Error: AGNES_API_KEY not set")
    return key

def _headers():
    return {"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"}

def _api_call(req, timeout=120):
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        sys.exit(f"API error {e.code}: {body}")
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        sys.exit(f"API request failed: {e}")

def create(prompt, mode="text2video", image_urls=None, width=1152, height=768, num_frames=121, frame_rate=24, seed=None, num_inference_steps=None, negative_prompt=None, poll=True, poll_interval=10, timeout=900, download=False, output_dir=None, dry_run=False, api_base=None):
    base = api_base or API_BASE

    if num_frames > 441:
        sys.exit(f"Error: num_frames must be <= 441, got {num_frames}")
    if (num_frames - 1) % 8 != 0:
        sys.exit(f"Error: num_frames must satisfy 8n+1, got {num_frames}")
    if not 1 <= frame_rate <= 60:
        sys.exit(f"Error: frame_rate must be 1-60, got {frame_rate}")

    body = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "frame_rate": frame_rate,
    }
    image_urls = image_urls or []
    if mode == "img2video" and len(image_urls) != 1:
        sys.exit("Error: img2video needs exactly one --image-url")
    if mode in ("multivideo", "keyframes") and len(image_urls) < 2:
        sys.exit(f"Error: {mode} needs at least two --image-url")
    # Agnes expects public image URLs (see agnes-ai-cli).
    if mode == "img2video":
        body["image"] = image_urls[0]
    elif mode == "multivideo":
        body["extra_body"] = {"image": image_urls}
    elif mode == "keyframes":
        body["extra_body"] = {"image": image_urls, "mode": "keyframes"}
    if seed is not None:
        body["seed"] = seed
    if num_inference_steps is not None:
        body["num_inference_steps"] = num_inference_steps
    if negative_prompt:
        body["negative_prompt"] = negative_prompt

    if dry_run:
        return {"dry_run": True, "request": body}

    req = urllib.request.Request(
        f"{base}/v1/videos",
        data=json.dumps(body).encode(),
        headers=_headers(),
        method="POST"
    )
    resp = _api_call(req)

    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    rid = resp.get("id") if isinstance(resp.get("id"), str) else None
    video_id = resp.get("video_id") or data.get("video_id") or (rid if rid and rid.startswith("video_") else None)
    task_id = resp.get("task_id") or data.get("task_id") or rid
    poll_id = video_id or task_id
    if not poll_id:
        sys.exit(f"Error: no video_id/task_id in response: {json.dumps(resp)[:500]}")

    result = {"task_id": task_id, "video_id": video_id, "status": resp.get("status", "queued")}

    if poll:
        return poll_video(poll_id, poll_interval, timeout, download, output_dir, base)
    return result

def _status_url(base, video_id):
    if video_id.startswith("task_"):
        return f"{base}/v1/videos/{urllib.parse.quote(video_id)}"
    return f"{base}/agnesapi?" + urllib.parse.urlencode({"video_id": video_id})

def _video_url(resp):
    meta = resp.get("metadata") if isinstance(resp.get("metadata"), dict) else {}
    res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
    for c in (meta.get("url"), resp.get("video_url"), resp.get("url"), resp.get("output_url"), res.get("video_url")):
        if isinstance(c, str) and c.startswith(("http://", "https://")):
            return c
    return None

def poll_video(video_id, poll_interval=10, timeout=900, download=False, output_dir=None, api_base=None):
    base = api_base or API_BASE
    start = time.time()

    while True:
        if time.time() - start > timeout:
            return {"video_id": video_id, "status": "timed_out"}

        req = urllib.request.Request(_status_url(base, video_id), headers=_headers())
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 503:  # service busy, keep waiting
                time.sleep(poll_interval)
                continue
            sys.exit(f"API error {e.code}: {e.read().decode()}")
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            sys.exit(f"API request failed: {e}")

        status = str(resp.get("status", resp.get("state", "unknown"))).lower()
        video_url = _video_url(resp)
        if status in ("completed", "succeeded", "success", "done") or (status == "unknown" and resp.get("completed_at") and video_url):
            result = {"video_id": video_id, "status": "completed", "video_url": video_url}
            if download and video_url:
                os.makedirs(output_dir or ".", exist_ok=True)
                local = os.path.join(output_dir or ".", f"agnes_video_{video_id[-12:]}.mp4")
                urllib.request.urlretrieve(video_url, local)
                result["local_path"] = local
            return result
        elif status in ("failed", "error", "cancelled", "canceled"):
            return {"video_id": video_id, "status": "failed", "error": resp.get("error", resp.get("message", "unknown"))}

        time.sleep(poll_interval)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["text2video", "img2video", "multivideo", "keyframes"])
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image-url", action="append")
    parser.add_argument("--width", type=int, default=1152)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--num-frames", type=int, default=121)
    parser.add_argument("--frame-rate", type=int, default=24)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--num-inference-steps", type=int)
    parser.add_argument("--negative-prompt")
    parser.add_argument("--no-poll", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from media import resolve
    image_urls = [resolve(u) for u in args.image_url] if args.image_url else None
    result = create(
        args.prompt, args.mode, image_urls,
        args.width, args.height, args.num_frames, args.frame_rate,
        args.seed, args.num_inference_steps, args.negative_prompt,
        not args.no_poll, args.poll_interval, args.timeout,
        args.download, args.output_dir, args.dry_run
    )
    if not args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2))
