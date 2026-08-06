import json, os, sys, time, urllib.error, urllib.request

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

def create(prompt, mode="text2video", image_b64s=None, width=1152, height=768, num_frames=121, frame_rate=24, seed=None, num_inference_steps=None, negative_prompt=None, poll=True, poll_interval=10, timeout=900, download=False, output_dir=None, dry_run=False, api_base=None):
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
    if mode == "img2video" and image_b64s:
        body["image"] = image_b64s[0]
    elif mode == "keyframes" and image_b64s:
        body["extra_body"] = {"image": image_b64s, "mode": "keyframes"}
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

    video_id = resp.get("video_id") or resp.get("id") or resp.get("data", {}).get("video_id")
    task_id = resp.get("task_id") or resp.get("id")

    result = {"task_id": task_id, "video_id": video_id, "status": "queued"}

    if poll and video_id:
        return poll_video(video_id, poll_interval, timeout, download, output_dir, base)
    return result

def poll_video(video_id, poll_interval=10, timeout=900, download=False, output_dir=None, api_base=None):
    base = api_base or API_BASE
    start = time.time()

    while True:
        if time.time() - start > timeout:
            return {"video_id": video_id, "status": "timed_out"}

        url = f"{base}/agnesapi?video_id={video_id}&model_name=agnes-video-v2.0"
        req = urllib.request.Request(url, headers=_headers())
        resp = _api_call(req)

        status = resp.get("status", resp.get("state", "unknown"))
        if status in ("completed", "succeeded", "done"):
            video_url = resp.get("video_url") or resp.get("url") or resp.get("result", {}).get("video_url")
            result = {"video_id": video_id, "status": "completed", "video_url": video_url}
            if download and video_url:
                os.makedirs(output_dir or ".", exist_ok=True)
                local = os.path.join(output_dir or ".", f"agnes_video_{video_id[:8]}.mp4")
                urllib.request.urlretrieve(video_url, local)
                result["local_path"] = local
            return result
        elif status in ("failed", "error"):
            return {"video_id": video_id, "status": "failed", "error": resp.get("error", resp.get("message", "unknown"))}

        time.sleep(poll_interval)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["text2video", "img2video", "keyframes"])
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
    from media import to_base64
    image_b64s = [to_base64(u) for u in args.image_url] if args.image_url else None
    result = create(
        args.prompt, args.mode, image_b64s,
        args.width, args.height, args.num_frames, args.frame_rate,
        args.seed, args.num_inference_steps, args.negative_prompt,
        not args.no_poll, args.poll_interval, args.timeout,
        args.download, args.output_dir, args.dry_run
    )
    if not args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2))
