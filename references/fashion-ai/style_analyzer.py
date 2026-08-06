from PIL import Image
from openai import OpenAI

import config
from utils import image_to_uri


def analyze_style(client: OpenAI, reference_images: list[Image.Image]) -> str:
    content = [
        {"type": "image_url", "image_url": {"url": image_to_uri(img)}}
        for img in reference_images
    ]
    content.append({
        "type": "text",
        "text": (
            "These are our top-selling fashion product photos.\n\n"
            "Analyze their common visual style in these dimensions:\n"
            "1. Scene / background setting\n"
            "2. Lighting and color tone\n"
            "3. Model pose and framing\n"
            "4. Overall mood and aesthetic\n\n"
            "Then, based on this analysis, write ONE concise image generation prompt "
            "(under 100 words) that captures this style. The prompt should describe "
            "a scene for a model wearing a new clothing item. "
            "Output ONLY the prompt, nothing else."
        ),
    })

    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=1024,
        temperature=0.7,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    msg = response.choices[0].message
    style_prompt = (msg.content or "").strip()
    if not style_prompt:
        reasoning = getattr(msg, "reasoning_content", None) or ""
        style_prompt = reasoning.strip()
    if not style_prompt:
        print(f"Warning: empty response from model. Raw: {msg}")
    else:
        print(f"\nStyle prompt from {config.LLM_MODEL}:\n{style_prompt}\n")
    return style_prompt
