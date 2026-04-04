from app.schemas import LanguageCode, ScriptPayload


def script_visual_segments(script: ScriptPayload) -> list[tuple[str, str]]:
    """(segment_id, spoken text) in narration order."""
    if script.conversational_turns:
        return [
            (f"turn_{i}", t.text.strip())
            for i, t in enumerate(script.conversational_turns)
        ]
    parts: list[tuple[str, str]] = [("hook", script.hook)]
    for i, fact in enumerate(script.facts):
        parts.append((f"fact_{i + 1}", fact))
    parts.append(("ending", script.ending))
    return parts


def _truncate_scene(s: str, max_len: int = 420) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _scene_snippet_for_image(
    topic: str,
    narration_snippet: str,
    visual_hint_en: str | None,
    language: LanguageCode,
) -> str:
    """Prefer English visual_hints from the script; avoid Devanagari in the image prompt for hi/mr."""
    hint = (visual_hint_en or "").strip()
    if hint:
        return _truncate_scene(hint)
    if language in ("hi", "mr"):
        tc = _truncate_scene((topic or "").strip(), 280)
        return f"Educational documentary scene about: {tc}. Visual storytelling only; no readable text."
    return _truncate_scene((narration_snippet or "").strip())


def build_slide_image_prompt(
    topic: str,
    narration_snippet: str,
    language: LanguageCode,
    *,
    visual_hint_en: str | None = None,
    reserve_product_hero_zone: bool = False,
    user_product_reference: bool = False,
) -> str:
    """Scene-only prompt for slide generators.

    Avoid internal segment ids, aspect-ratio jargon, or long instruction blocks in the
    string — image models often paint those as visible captions. Aspect ratio is set via API.
    For Hindi/Marathi narration, pass visual_hint_en (English) so models do not garble Devanagari.
    """
    scene = _scene_snippet_for_image(topic, narration_snippet, visual_hint_en, language)
    topic_clean = (topic or "").strip()
    audience = {
        "en": "English-speaking",
        "hi": "Hindi-speaking",
        "mr": "Marathi-speaking",
    }[language]

    no_indic = ""
    if language in ("hi", "mr"):
        no_indic = (
            "Never render Devanagari, Hindi, Marathi, or other Indic script in the image — "
            "only wordless visual. "
        )

    product_zone = ""
    if user_product_reference:
        product_zone = (
            "The first attached image is the user's real product (bottle, jar, or package) with its true label and colors. "
            "Show a person naturally holding THIS EXACT product in their hands in the scene—grip and fingers must look realistic. "
            "Match bottle shape, cap, label layout, and colors to the reference; do not invent a different package. "
            "Do not add a second duplicate of the product as a floating inset, corner cutout, or picture-in-picture. "
            "The held product should be the clear hero in frame. "
        )
    elif reserve_product_hero_zone:
        product_zone = (
            "CRITICAL: The lower-left ~40% of the frame is RESERVED EMPTY for a real product photo overlay—"
            "keep that zone visually simple: soft counter edge, plain cloth, or gentle out-of-focus blur only. "
            "Do not draw any bottle, jar, package, label, or readable branding in that reserved zone. "
            "Place the main scene action, props, and any hero product (if shown) in the center or right half only. "
        )

    if user_product_reference:
        tail = (
            "Photorealistic documentary style. Only lettering that belongs on the reference product label may appear; "
            "add no other readable words, captions, slogans, or watermarks in the scene."
        )
    else:
        tail = (
            "The image must contain no letters, numbers, captions, subtitles, labels, watermarks, or logos anywhere."
        )

    return (
        f"Photorealistic cinematic photograph for an educational video for {audience} audiences. "
        f"Topic: {topic_clean}. "
        f"{no_indic}"
        f"{product_zone}"
        f"Depict this idea as a single clear scene (do not paint this brief as readable text): {scene}. "
        "One main subject, shot on a professional cinema camera, shallow depth of field, natural lighting, "
        "real-world textures and materials, lifelike skin tones, no cartoon or illustration style. "
        f"{tail}"
    )
