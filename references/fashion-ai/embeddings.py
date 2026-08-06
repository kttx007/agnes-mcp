import time

import numpy as np
import requests as req
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from tqdm import tqdm

import config
from utils import image_to_uri


def get_image_embeddings(images: list[Image.Image], batch_size: int = None) -> np.ndarray:
    if batch_size is None:
        batch_size = config.EMBED_BATCH_SIZE
    all_embs = []
    for i in tqdm(range(0, len(images), batch_size), desc="Encoding images"):
        batch = images[i : i + batch_size]
        inputs = [
            {"content": [{"type": "image_url", "image_url": {"url": image_to_uri(img, max_size=512)}}]}
            for img in batch
        ]
        resp = req.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
            json={"model": config.EMBED_MODEL, "input": inputs},
            timeout=120,
        )
        data = resp.json()
        if "data" not in data:
            print(f"API error: {data}")
            continue
        for item in sorted(data["data"], key=lambda x: x["index"]):
            all_embs.append(item["embedding"])
        time.sleep(0.5)
    return np.array(all_embs, dtype=np.float32)


def get_text_embedding(text: str) -> np.ndarray:
    resp = req.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json={"model": config.EMBED_MODEL, "input": text},
        timeout=60,
    )
    return np.array(resp.json()["data"][0]["embedding"], dtype=np.float32)


def build_tfidf(descriptions: list[str]):
    tfidf = TfidfVectorizer(stop_words="english", max_features=500)
    tfidf_matrix = tfidf.fit_transform(descriptions)
    sparse_vectors = [sparse_to_dict(tfidf_matrix[i]) for i in range(len(descriptions))]
    return tfidf, sparse_vectors


def sparse_to_dict(sparse_row) -> dict[int, float]:
    coo = sparse_row.tocoo()
    return {int(i): float(v) for i, v in zip(coo.col, coo.data)}
