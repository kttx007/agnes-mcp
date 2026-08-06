import io
import base64
import os

from PIL import Image

import config


def image_to_uri(img: Image.Image, max_size: int = 1024) -> str:
    img = img.copy()
    w, h = img.size
    if max(w, h) > max_size:
        r = max_size / max(w, h)
        img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


def extract_images(response) -> list[Image.Image]:
    images = []
    raw = response.model_dump()
    msg = raw["choices"][0]["message"]
    if "images" in msg and msg["images"]:
        for img_data in msg["images"]:
            url = img_data["image_url"]["url"]
            b64 = url.split(",", 1)[1]
            images.append(Image.open(io.BytesIO(base64.b64decode(b64))))
    if not images and isinstance(msg.get("content"), list):
        for part in msg["content"]:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = part["image_url"]["url"]
                if url.startswith("data:image"):
                    b64 = url.split(",", 1)[1]
                    images.append(Image.open(io.BytesIO(base64.b64decode(b64))))
    return images


def load_image(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


def save_image(img: Image.Image, name: str, subdir: str = "") -> str:
    out = os.path.join(config.OUTPUT_DIR, subdir)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    img.save(path)
    return path
