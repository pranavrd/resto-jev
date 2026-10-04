"""Local vision-language model (Apple Silicon, MLX) for describing a building's ground floor from a street photo.

The caption is evidence for Jev, not a decision: it is read as text by the D1 to D3 questions at tier 1.
"""

import time
from dataclasses import dataclass

MODEL_ID = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"  # Qwen Research License (non-commercial); 7B is Apache-2.0

CAPTION_PROMPT_V1 = (
    "This street photo was taken looking toward one particular building, which is near the centre of the picture. "
    "Describe only the ground floor of that building: whether it has a storefront, a shop window, an awning or "
    "an entrance with a sign, or whether it looks like a house (front door, steps, ordinary windows). "
    "Quote any sign text you can read exactly. If the ground floor is not visible, say so. "
    "Answer in at most three short sentences."
)


# v2: neutral wording. v1 offered "storefront or house" and the model answered "storefront" almost every time;
# it also reported traffic and street-name signs as shop signs.
CAPTION_PROMPT_V2 = (
    "Describe the ground floor of the building at the centre of this street photo: what is there at street "
    "level, for example an entrance door with steps, a shop window, an awning, a shop sign, a garage door, or "
    "plain walls. Quote text only if it is on that building's own sign or awning. Ignore street-name signs, "
    "traffic signs, parking signs and the signs of other buildings. If the ground floor is hidden or too far "
    "to see, say exactly 'ground floor not visible'. Do not guess. Answer in at most two short sentences."
)

# v3: structured. v2's explicit refusal phrase made the model answer "ground floor not visible" for every photo, so
# uncertainty is now one option in a short list rather than an all-or-nothing escape.
CAPTION_PROMPT_V3 = (
    "Look at the building at the centre of this street photo and answer in exactly this format.\n"
    "Street level: <one of: entrance door with steps, shop window or storefront, garage door, plain wall, "
    "not visible>.\n"
    "Awning or sign on that building: <the exact text on that building's own sign or awning, or none>.\n"
    "Ignore street-name signs, traffic signs, parking signs and other buildings' signs."
)

CAPTION_PROMPTS = {"v1": CAPTION_PROMPT_V1, "v2": CAPTION_PROMPT_V2, "v3": CAPTION_PROMPT_V3}


@dataclass(frozen=True)
class Caption:
    text: str
    seconds: float
    prompt_tokens: int
    generated_tokens: int
    peak_memory_gb: float


def load_vlm(model_id: str = MODEL_ID):
    from mlx_vlm import load
    from mlx_vlm.utils import load_config

    model, processor = load(model_id)
    return model, processor, load_config(model_id)


def caption(vlm, image_path: str, prompt: str = CAPTION_PROMPT_V1, max_tokens: int = 110) -> Caption:
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    model, processor, config = vlm
    formatted = apply_chat_template(processor, config, prompt, num_images=1)
    t0 = time.perf_counter()
    r = generate(model, processor, formatted, image=[image_path], max_tokens=max_tokens, verbose=False, temperature=0.0)
    return Caption(
        text=r.text.strip(), seconds=time.perf_counter() - t0, prompt_tokens=r.prompt_tokens,
        generated_tokens=r.generation_tokens, peak_memory_gb=r.peak_memory,
    )


@dataclass(frozen=True)
class ParsedCaption:
    street_level: str  # entrance door with steps | shop window or storefront | garage door | plain wall | not visible | unknown
    sign: str | None  # the building's own sign text, or None


_LEVELS = ("entrance door with steps", "shop window or storefront", "garage door", "plain wall", "not visible")


def parse_caption(text: str) -> ParsedCaption:
    """Read a structured v3 caption. Echoed prompt text or 'none' means no sign; an unlisted street-level answer is 'unknown'."""
    level, sign = "unknown", None
    for line in text.splitlines():
        low = line.lower().strip()
        if low.startswith("street level:"):
            value = low.split(":", 1)[1].strip().rstrip(".")
            level = next((lv for lv in _LEVELS if lv in value), "unknown")
        elif low.startswith("awning or sign"):
            value = line.split(":", 1)[1].strip().strip("\"'").rstrip(".")
            if value and value.lower() not in ("none", "n/a", "no sign") and "exact text" not in value.lower():
                sign = value
    return ParsedCaption(level, sign)
