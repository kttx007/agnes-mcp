#!/usr/bin/env python3
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import text, image, video, translate, media

def cmd_text(args):
    if not args.prompt and not args.message and not args.image_url:
        sys.exit("Error: --prompt, --message, or --image-url required")
    if not args.prompt and args.message:
        args.prompt = ""
    image_b64s = [media.to_base64(u) for u in (args.image_url or [])] if args.image_url else None
    translated = args.prompt
    if args.prompt and not args.no_translate and translate.needs_translation(args.prompt):
        translated = translate.translate(args.prompt)
        if args.verbose:
            print(f"[translated] {args.prompt} -> {translated}", file=sys.stderr)
    result = text.chat(
        translated, system=args.system, messages=args.message,
        stream=args.stream, temperature=args.temperature, top_p=args.top_p,
        max_tokens=args.max_tokens, tools_json=args.tools_json,
        tool_choice=args.tool_choice, json_output=args.json_output,
        dry_run=args.dry_run, image_b64s=image_b64s
    )
    if args.dry_run:
        print(json.dumps(result, indent=2))
    elif args.json_output and isinstance(result, dict):
        print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_image(args):
    translated = args.prompt
    if not args.no_translate and translate.needs_translation(args.prompt):
        translated = translate.translate(args.prompt)
        if args.verbose:
            print(f"[translated] {args.prompt} -> {translated}", file=sys.stderr)
    image_b64s = [media.to_base64(u) for u in (args.image_url or [])] if args.image_url else None
    result = image.generate(
        translated, mode=args.mode, image_b64s=image_b64s,
        size=args.size, output_dir=args.output_dir, dry_run=args.dry_run
    )
    if args.dry_run:
        print(json.dumps(result, indent=2))
    else:
        for p in result:
            print(p)

def cmd_video(args):
    translated = args.prompt
    if not args.no_translate and translate.needs_translation(args.prompt):
        translated = translate.translate(args.prompt)
        if args.verbose:
            print(f"[translated] {args.prompt} -> {translated}", file=sys.stderr)
    image_b64s = [media.to_base64(u) for u in (args.image_url or [])] if args.image_url else None
    result = video.create(
        translated, mode=args.mode, image_b64s=image_b64s,
        width=args.width, height=args.height, num_frames=args.num_frames,
        frame_rate=args.frame_rate, seed=args.seed,
        num_inference_steps=args.num_inference_steps,
        negative_prompt=args.negative_prompt,
        poll=not args.no_poll, poll_interval=args.poll_interval,
        timeout=args.timeout, download=args.download,
        output_dir=args.output_dir, dry_run=args.dry_run
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_video_poll(args):
    if args.dry_run:
        print(json.dumps({"dry_run": True, "video_id": args.video_id}, indent=2))
        return
    result = video.poll_video(args.video_id, args.poll_interval, args.timeout, args.download, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))

def cmd_smoke_test(args):
    print("=== Agnes-AI Smoke Test ===")
    # ponytail: smoke test runs text and image; video optional due to time
    print("[text] testing basic chat...")
    r = text.chat("Say hello", dry_run=True)
    assert r["dry_run"]
    print("  PASS (dry-run)")

    print("[text] testing streaming...")
    r = text.chat("Count to 3", stream=True, dry_run=True)
    assert r["dry_run"]
    print("  PASS (dry-run)")

    print("[text] testing describe (image-to-text)...")
    r = text.chat("Describe this", image_b64s=["dGVzdA=="], dry_run=True)
    assert r["dry_run"]
    print("  PASS (dry-run)")

    print("[image] testing text2img...")
    r = image.generate("test", dry_run=True)
    assert r["dry_run"]
    print("  PASS (dry-run)")

    print("[image] testing img2img (dry-run)...")
    r = image.generate("test", mode="img2img", image_b64s=["dGVzdA=="], dry_run=True)
    assert r["dry_run"]
    print("  PASS (dry-run)")

    if args.video_case:
        print(f"[video] testing {args.video_case}...")
        r = video.create("test", mode=args.video_case, dry_run=True)
        assert r["dry_run"]
        print("  PASS (dry-run)")

    print("=== All smoke tests passed ===")

def cmd_setup(args):
    key = input("Enter your Agnes AI API Key: ").strip()
    if not key:
        print("Aborted.")
        return
    shell = os.path.basename(os.environ.get("SHELL", "/bin/zsh"))
    rc_files = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "sh": "~/.profile"}
    rc = rc_files.get(shell, "~/.profile")
    rc_path = os.path.expanduser(rc)
    export_line = f'\nexport AGNES_API_KEY="{key}"\n'
    if os.path.exists(rc_path):
        with open(rc_path) as f:
            content = f.read()
        if "AGNES_API_KEY" in content:
            import re
            content = re.sub(r'export AGNES_API_KEY="[^"]*"', f'export AGNES_API_KEY="{key}"', content)
        else:
            content += export_line
        with open(rc_path, "w") as f:
            f.write(content)
    else:
        with open(rc_path, "w") as f:
            f.write(export_line)
    print(f"API Key saved to {rc}")
    print("Run: source", rc)

def main():
    parser = argparse.ArgumentParser(prog="agnes", description="Agnes-AI -- text, image, video generation")
    parser.add_argument("--dry-run", action="store_true", help="Validate request without calling API")
    parser.add_argument("--no-translate", action="store_true", help="Disable automatic prompt translation")
    parser.add_argument("--verbose", action="store_true", help="Print debug info to stderr")
    sub = parser.add_subparsers(dest="command")

    global_args = argparse.ArgumentParser(add_help=False)
    global_args.add_argument("--dry-run", action="store_true")
    global_args.add_argument("--no-translate", action="store_true")
    global_args.add_argument("--verbose", action="store_true")

    # text
    p_text = sub.add_parser("text", parents=[global_args], help="Generate text with agnes-2.0-flash")
    p_text.add_argument("--prompt", help="Prompt (optional when --image-url is provided)")
    p_text.add_argument("--system")
    p_text.add_argument("--message", action="append")
    p_text.add_argument("--image-url", action="append")
    p_text.add_argument("--stream", action="store_true")
    p_text.add_argument("--temperature", type=float, default=0.7)
    p_text.add_argument("--top-p", type=float, default=0.9)
    p_text.add_argument("--max-tokens", type=int, default=4096)
    p_text.add_argument("--tools-json")
    p_text.add_argument("--tool-choice")
    p_text.add_argument("--json-output", action="store_true")
    p_text.set_defaults(func=cmd_text)

    # image
    p_img = sub.add_parser("image", parents=[global_args], help="Generate images with agnes-image-2.1-flash")
    p_img.add_argument("mode", choices=["text2img", "img2img", "compose"])
    p_img.add_argument("--prompt", required=True)
    p_img.add_argument("--image-url", action="append")
    p_img.add_argument("--size", default="1024x768")
    p_img.add_argument("--output-dir")
    p_img.set_defaults(func=cmd_image)

    # video
    p_vid = sub.add_parser("video", parents=[global_args], help="Generate videos with agnes-video-v2.0")
    p_vid.add_argument("mode", choices=["text2video", "img2video", "keyframes"])
    p_vid.add_argument("--prompt", required=True)
    p_vid.add_argument("--image-url", action="append")
    p_vid.add_argument("--width", type=int, default=1152)
    p_vid.add_argument("--height", type=int, default=768)
    p_vid.add_argument("--num-frames", type=int, default=121)
    p_vid.add_argument("--frame-rate", type=int, default=24)
    p_vid.add_argument("--seed", type=int)
    p_vid.add_argument("--num-inference-steps", type=int)
    p_vid.add_argument("--negative-prompt")
    p_vid.add_argument("--no-poll", action="store_true")
    p_vid.add_argument("--poll-interval", type=int, default=10)
    p_vid.add_argument("--timeout", type=int, default=900)
    p_vid.add_argument("--download", action="store_true")
    p_vid.add_argument("--output-dir")
    p_vid.set_defaults(func=cmd_video)

    # video poll
    p_poll = sub.add_parser("poll", parents=[global_args], help="Poll video result by video_id")
    p_poll.add_argument("video_id")
    p_poll.add_argument("--poll-interval", type=int, default=10)
    p_poll.add_argument("--timeout", type=int, default=900)
    p_poll.add_argument("--download", action="store_true")
    p_poll.add_argument("--output-dir")
    p_poll.set_defaults(func=cmd_video_poll)

    # smoke-test
    p_test = sub.add_parser("smoke-test", parents=[global_args], help="Run end-to-end smoke tests (dry-run mode)")
    p_test.add_argument("--video-case", choices=["text2video", "img2video", "keyframes"])
    p_test.set_defaults(func=cmd_smoke_test)

    # setup
    p_setup = sub.add_parser("setup", parents=[global_args], help="Save AGNES_API_KEY to shell profile")
    p_setup.set_defaults(func=cmd_setup)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
