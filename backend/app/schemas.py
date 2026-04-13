from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RedeemBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)

LanguageCode = Literal["en", "hi", "mr"]

DialogueSpeaker = Literal["male", "female"]


class DialogueTurn(BaseModel):
    speaker: DialogueSpeaker
    text: str = Field(..., min_length=1, max_length=1200)


class GenerateRequest(BaseModel):
    # Keep max_length in sync with USER_PROMPT_MAX_CHARS in app.main.
    topic: str = Field(..., min_length=1, max_length=1000)
    language: LanguageCode = "en"


class ScriptPayload(BaseModel):
    hook: str
    facts: list[str] = Field(..., min_length=0, max_length=8)
    ending: str
    full_script_plain: str
    # English-only scene lines for image models (hook + each fact + ending); avoids bad Devanagari in slides.
    visual_segments_en: list[str] = Field(default_factory=list)
    # When non-empty (Enhance conversational): one slide + timing segment per turn; alternating voices in TTS.
    conversational_turns: list[DialogueTurn] = Field(default_factory=list)

    @model_validator(mode="after")
    def visual_segments_en_aligns(self) -> ScriptPayload:
        if self.conversational_turns:
            n = len(self.conversational_turns)
            if n < 6:
                raise ValueError(f"conversational_turns must have at least 6 lines, got {n}")
            for i in range(n - 1):
                if self.conversational_turns[i].speaker == self.conversational_turns[i + 1].speaker:
                    raise ValueError(
                        "conversational_turns must alternate male and female speakers on each line"
                    )
            if len(self.visual_segments_en) != n:
                raise ValueError(
                    f"visual_segments_en must have one entry per conversational line ({n}), "
                    f"got {len(self.visual_segments_en)}"
                )
            return self
        if len(self.facts) < 2:
            raise ValueError("facts must have at least 2 items when not using conversational_turns")
        if not self.visual_segments_en:
            return self
        expected = 2 + len(self.facts)
        if len(self.visual_segments_en) != expected:
            raise ValueError(
                f"visual_segments_en must have {expected} entries (hook + facts + ending), "
                f"got {len(self.visual_segments_en)}"
            )
        return self


class GenerateResponse(BaseModel):
    """Same-origin media URLs for the browser UI (no server filesystem paths)."""

    job_id: str
    target_duration_seconds: int = 59
    script: ScriptPayload
    mp3_url: str
    mp4_url: str
    video_width: int
    video_height: int
    # Set when the client sent content_format / output_quality (new UI); None if both omitted (legacy API).
    content_format_applied: str | None = None
    output_quality_applied: str | None = None
    tts_provider: Literal["google", "elevenlabs", "coqui"]
    visual_mode: Literal[
        "gemini_native_image_slideshow",
        "vertex_gemini_image_slideshow",
        "google_imagen_slideshow",
        "nano_banana_slideshow",
        "title_card",
    ]
    # When visual_mode is title_card: why slides were skipped or what failed (Imagen rate limits, etc.)
    visual_detail: str | None = None
    branding_logo_applied: bool = False
    product_image_applied: bool = False
    cta_image_applied: bool = False
    address_applied: bool = False
    thumbnail_attached: bool = False
