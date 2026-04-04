"""Face-swap service using InsightFace + inswapper_128.

Swaps the user's face into a template base image, preserving the template's
pose, clothing, text, and background pixel-perfectly.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get("FACE_SWAP_MODEL_DIR", str(Path.home() / ".insightface")))
INSWAPPER_PATH = MODEL_DIR / "inswapper_128.onnx"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "templates"

FACE_SWAP_TEMPLATES = frozenset({
    "ink_sketch", "bold_text", "street_art", "sticky_notes", "polaroid",
})


class FaceSwapError(Exception):
    pass


_face_app = None
_swapper = None


def _get_face_app():
    global _face_app
    if _face_app is None:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name="buffalo_l",
            root=str(MODEL_DIR),
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _face_app = app
        logger.info("InsightFace buffalo_l loaded from %s", MODEL_DIR)
    return _face_app


def _detect_faces(face_app, img_cv: np.ndarray, label: str):
    """Try progressively more aggressive detection strategies."""
    faces = face_app.get(img_cv)
    if faces:
        return faces

    logger.info("Face detect (%s): standard failed, trying enhanced contrast", label)
    enhanced = _enhance_for_detection(img_cv)
    faces = face_app.get(enhanced)
    if faces:
        return faces

    logger.info("Face detect (%s): enhanced failed, trying lower threshold", label)
    old_thresh = face_app.det_model.det_thresh if hasattr(face_app, "det_model") else 0.5
    try:
        if hasattr(face_app, "det_model"):
            face_app.det_model.det_thresh = 0.15
        faces = face_app.get(enhanced)
        if faces:
            return faces
    finally:
        if hasattr(face_app, "det_model"):
            face_app.det_model.det_thresh = old_thresh

    return []


def _enhance_for_detection(img_cv: np.ndarray) -> np.ndarray:
    """Enhance a stylized/low-contrast image to help face detection."""
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray)
    enhanced = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
    blended = cv2.addWeighted(img_cv, 0.5, enhanced, 0.5, 0)
    return blended


def _get_swapper():
    global _swapper
    if _swapper is None:
        import insightface

        if not INSWAPPER_PATH.is_file():
            raise FaceSwapError(f"inswapper_128.onnx not found at {INSWAPPER_PATH}")
        _swapper = insightface.model_zoo.get_model(
            str(INSWAPPER_PATH),
            providers=["CPUExecutionProvider"],
        )
        logger.info("inswapper_128 loaded from %s", INSWAPPER_PATH)
    return _swapper


def _pil_to_cv2(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv2_to_pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def _largest_face(faces):
    """Return the face with the largest bounding-box area."""
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


def _swap_face_sync(
    template_path: Path,
    user_photo_bytes: bytes,
    out_path: Path,
) -> None:
    face_app = _get_face_app()
    swapper = _get_swapper()

    template_cv = _pil_to_cv2(Image.open(template_path))
    user_cv = _pil_to_cv2(Image.open(io.BytesIO(user_photo_bytes)))

    template_faces = _detect_faces(face_app, template_cv, "template")
    if not template_faces:
        raise FaceSwapError("No face detected in template image")

    user_faces = _detect_faces(face_app, user_cv, "user")
    if not user_faces:
        raise FaceSwapError("No face detected in uploaded photo")

    target_face = _largest_face(template_faces)
    source_face = _largest_face(user_faces)

    result = swapper.get(template_cv, target_face, source_face, paste_back=True)

    result_pil = _cv2_to_pil(result)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_pil.save(out_path, "PNG")
    logger.info("Face swap OK: template=%s -> %s", template_path.name, out_path.name)


async def swap_face(
    template_name: str,
    user_photo_bytes: bytes,
    out_path: Path,
) -> None:
    """Swap the user's face into the named template image.

    Runs the CPU-heavy work in a thread so the event loop stays responsive.
    Raises ``FaceSwapError`` if face detection fails on either image.
    """
    template_path = TEMPLATES_DIR / f"{template_name}.png"
    if not template_path.is_file():
        raise FaceSwapError(f"Template base image not found: {template_name}")

    await asyncio.to_thread(_swap_face_sync, template_path, user_photo_bytes, out_path)
