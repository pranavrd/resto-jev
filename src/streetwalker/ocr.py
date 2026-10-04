"""Read text from a street photo with Apple's Vision framework (on-device, no model download, macOS only).

Each hit comes with a bounding box, so text can be attributed by position: in a view aimed at a building, text
near the centre belongs to that building and text toward the sides belongs to its neighbours.
"""

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float
    cx: float  # box centre, 0 = left edge, 1 = right edge of the picture
    cy: float  # 0 = top, 1 = bottom
    w: float  # box width as a share of the picture width
    h: float  # box height as a share of the picture height


def _recognise(handler, language_correction: bool) -> list[TextBox]:
    import Vision

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(language_correction)
    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision text recognition failed: {err}")
    out = []
    for obs in request.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        box = obs.boundingBox()  # normalised, origin at the bottom-left
        out.append(TextBox(
            str(cand[0].string()), float(cand[0].confidence()),
            box.origin.x + box.size.width / 2, 1 - (box.origin.y + box.size.height / 2),
            box.size.width, box.size.height,
        ))
    return out


def read_text(image, language_correction: bool = False) -> list[TextBox]:
    """Recognise text in a PIL image or an image file path. The pixels are handed to Vision as PNG data: reading the
    same crop from a JPEG file returned nothing while the PNG returned text. Language correction is off by default:
    it 'fixes' business names into dictionary words."""
    import io

    import Foundation
    import Vision
    from PIL import Image

    img = Image.open(image) if isinstance(image, (str, os.PathLike)) else image
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    data = Foundation.NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
    return _recognise(Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {}), language_correction)


# Text that is not a business sign: street furniture, traffic and parking signs, address numbers.
_NOT_SIGNS = re.compile(
    r"^(stop|one way|do not enter|no parking|parking|no stopping|no standing|walk|don'?t walk|yield|wrong way|"
    r"bike lane|speed limit.*|st|ave|avenue|street|rd|road|ln|lane|open|closed|exit|enter|push|pull|"
    r"tow zone|tow away|permit.*|zone.*|rpp|loading|handicap|reserved)$", re.IGNORECASE)


def is_candidate_sign(t: TextBox, min_conf: float = 0.5, min_height: float = 0.012) -> bool:
    text = t.text.strip()
    letters = sum(c.isalpha() for c in text)
    if t.confidence < min_conf or t.h < min_height or letters < 3 or letters < len(text) * 0.5:
        return False
    return not _NOT_SIGNS.match(text)


def split_by_position(boxes: list[TextBox], centre: tuple[float, float] = (0.28, 0.72)) -> tuple[list[str], list[str]]:
    """(text near the centre of the picture, text toward the sides), keeping only plausible business signs."""
    middle, sides = [], []
    for b in boxes:
        if not is_candidate_sign(b):
            continue
        (middle if centre[0] <= b.cx <= centre[1] else sides).append(b.text.strip())
    return middle, sides


_GENERIC = {"llc", "inc", "co", "corp", "company", "the", "and", "of", "ltd", "lp", "dba", "restaurant", "shop", "store",
            "holdings", "group", "services", "enterprises", "philadelphia", "phila", "south", "north", "east", "west"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) >= 4 and t not in _GENERIC}


def _squash(s: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", s.lower()))


def name_match(texts: list[str], business_name: str, cutoff: float = 0.75) -> bool:
    """Does any recognised text plausibly spell part of the licensed business name?

    Compares letters-only strings so spacing and punctuation do not matter ("MOON, IGHT" against "MoonNight LLC"):
    the text can be close to the whole name, a substring of it, or close to one of its significant words."""
    from difflib import SequenceMatcher

    name = _squash(business_name)
    words = _tokens(business_name)
    for t in texts:
        sq = _squash(t)
        if len(sq) < 4:
            continue
        if SequenceMatcher(None, sq, name).ratio() >= cutoff or (len(sq) >= 5 and sq in name):
            return True
        if any(SequenceMatcher(None, sq, w).ratio() >= cutoff + 0.05 or (len(w) >= 5 and w in sq) for w in words):
            return True
    return False
