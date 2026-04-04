import json
import logging
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from app.config import Settings
from app.schemas import DialogueTurn, LanguageCode, ScriptPayload

logger = logging.getLogger(__name__)


def _facts_bounds(target_seconds: int) -> tuple[int, int]:
    if target_seconds <= 59:
        return (2, 4)
    if target_seconds <= 120:
        return (3, 5)
    return (5, 8)


def _word_target_range(target_seconds: int) -> tuple[int, int]:
    # ~90–150 wpm band; avoid forcing a 60-word floor on 30s scripts (was inflating length).
    low = max(28, int(target_seconds * 1.5))
    high = max(low + 8, int(target_seconds * 2.45))
    return (low, high)


def _conversational_turn_bounds(target_seconds: int) -> tuple[int, int]:
    """Min/max dialogue lines — each line is one slide + one image API call.

    Previously bounds used target_seconds//4 .. target_seconds//2 (~15–28 turns for ~60s),
    which blew past monologue slide counts (hook + 2–4 facts + ending ≈ 5–7) and caused
    long jobs and proxy timeouts. Align with that ballpark per duration.
    """
    if target_seconds <= 45:
        return (6, 7)
    if target_seconds <= 59:
        return (6, 8)
    if target_seconds <= 90:
        return (7, 10)
    if target_seconds <= 120:
        return (8, 12)
    if target_seconds <= 180:
        return (10, 14)
    if target_seconds <= 240:
        return (12, 16)
    return (14, 20)


def _build_conversational_script_json_schema(turns_min: int, turns_max: int) -> dict[str, Any]:
    return {
        "name": "ConversationalEducationalScript",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "turns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "speaker": {
                                "type": "string",
                                "enum": ["male", "female"],
                                "description": "Who speaks this line; must alternate with previous line.",
                            },
                            "text": {
                                "type": "string",
                                "description": "Spoken line only; no speaker labels; natural Q&A or explanation.",
                            },
                        },
                        "required": ["speaker", "text"],
                        "additionalProperties": False,
                    },
                    "minItems": turns_min,
                    "maxItems": turns_max,
                },
                "visual_segments_en": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": turns_min,
                    "maxItems": turns_max,
                    "description": (
                        "English-only scene prompts, one per turn, same order as turns. "
                        "Latin/ASCII only; short concrete scenes for AI slides."
                    ),
                },
            },
            "required": ["turns", "visual_segments_en"],
            "additionalProperties": False,
        },
    }


def _middle_turn_texts_to_facts(middle: list[str]) -> list[str]:
    """Map middle dialogue lines into 2–8 fact strings for legacy hook/facts/ending fields."""
    if len(middle) >= 8:
        return _merge_text_groups(middle, 8)
    if len(middle) >= 2:
        return middle[:8]
    if len(middle) == 1:
        return [middle[0], middle[0]]
    return ["Let's unpack this together.", "Here's what matters most."]


def _merge_text_groups(lines: list[str], k: int) -> list[str]:
    n = len(lines)
    if n <= k:
        return lines
    out: list[str] = []
    start = 0
    for i in range(k):
        end = (n * (i + 1)) // k
        chunk = " ".join(lines[start:end]).strip()
        if chunk:
            out.append(chunk)
        start = end
    while len(out) < 2:
        out.append(out[-1] if out else "Key point.")
    return out[:8]


def _payload_from_conversational_dict(data: dict[str, Any]) -> ScriptPayload:
    turns = [DialogueTurn.model_validate(t) for t in data["turns"]]
    visual = data["visual_segments_en"]
    full_plain = "\n\n".join(t.text.strip() for t in turns)
    hook = turns[0].text.strip()
    ending = turns[-1].text.strip()
    middle = [t.text.strip() for t in turns[1:-1]]
    facts = _middle_turn_texts_to_facts(middle)
    return ScriptPayload(
        hook=hook,
        facts=facts,
        ending=ending,
        full_script_plain=full_plain,
        visual_segments_en=visual,
        conversational_turns=turns,
    )


def _build_conversational_prompts(
    topic: str,
    language: LanguageCode,
    target_seconds: int,
    turns_min: int,
    turns_max: int,
) -> tuple[str, str]:
    w_lo, w_hi = _word_target_range(target_seconds)
    lang_line = _language_instruction(language)
    system = (
        "You write educational **dialogue** for short videos: two speakers (male and female voices) "
        "who help the viewer understand one topic. "
        "Strict rules: "
        f"(1) Produce between {turns_min} and {turns_max} turns in `turns`. "
        "(2) **Alternate speakers every line**: if one line is male, the next must be female, then male, etc. "
        "(3) Make it dynamic: questions, reactions, short clarifications, analogies—like a curious learner "
        "and a clear explainer (either gender can ask or answer; mix questions and answers naturally). "
        "(4) Each `text` is only what that person says—no names like 'Ravi:', no stage directions. "
        "(5) Keep total length suitable for roughly "
        f"{target_seconds} seconds spoken (~{w_lo}–{w_hi} words combined). "
        "(6) `visual_segments_en` must have the **same count** as `turns`, in order: one English-only "
        "scene description per line (concrete subject/setting/mood; ASCII only). "
        "Match each scene loosely to what is being discussed on that line."
    )
    user = (
        f"Topic: {topic.strip()}\n"
        f"{lang_line}\n"
        f"Target total spoken duration: about {target_seconds} seconds (~{w_lo}–{w_hi} words)."
    )
    return system, user


def _build_script_json_schema(facts_min: int, facts_max: int) -> dict[str, Any]:
    return {
        "name": "EducationalScript",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "hook": {
                    "type": "string",
                    "description": "Spoken hook; attention-grabbing opening.",
                },
                "facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": facts_min,
                    "maxItems": facts_max,
                    "description": f"{facts_min}–{facts_max} spoken key facts or sections.",
                },
                "ending": {
                    "type": "string",
                    "description": "Closing line: call to action or brief summary.",
                },
                "full_script_plain": {
                    "type": "string",
                    "description": "Full narration as one string for TTS, with natural pauses (newlines ok).",
                },
                "visual_segments_en": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": facts_min + 2,
                    "maxItems": facts_max + 2,
                    "description": (
                        "English-only visual scene prompts for AI images, same order as spoken segments: "
                        "hook, then one per fact, then ending. Latin/ASCII only; no Devanagari. "
                        "Short concrete scenes (subject, setting, action)."
                    ),
                },
            },
            "required": ["hook", "facts", "ending", "full_script_plain", "visual_segments_en"],
            "additionalProperties": False,
        },
    }


def _language_instruction(language: LanguageCode) -> str:
    if language == "en":
        return (
            "Write the entire script in English using Indian English: natural phrasing, "
            "vocabulary, and examples as an Indian educator would use (Indian context where "
            "it fits the topic)."
        )
    if language == "hi":
        return (
            "Write in natural Hinglish: use Hindi in Devanagari for most of the narration, "
            "and English words in Latin script for brands, tech terms, and short phrases "
            "where Indian speakers typically mix languages. The result should sound like "
            "conversational Indian speech, not fully formal Hindi only."
        )
    return (
        "Write in natural, conversational Marathi for video narration, in Devanagari. "
        "Use spoken Marathi like everyday Pune/Mumbai conversation — not formal, bookish, "
        "or Sanskritized prose. Prefer short, flowing sentences. Weave in natural fillers "
        "and connectors such as \"आणि\", \"म्हणून\", and \"आणि हो\" where they sound right. "
        "Where urban speakers naturally slip in English, keep it light: most narration stays "
        "Marathi in Devanagari; for common loanwords use natural Devanagari transliteration "
        "(e.g. परफेक्ट, टेस्ट, हेल्दी) or Latin for brands and sharp tech terms, as people "
        "actually say them. The script should sound like a person talking to the viewer, "
        "not someone reading aloud from a textbook."
    )


def _build_prompts(
    topic: str,
    language: LanguageCode,
    target_seconds: int,
    facts_min: int,
    facts_max: int,
) -> tuple[str, str]:
    w_lo, w_hi = _word_target_range(target_seconds)
    lang_line = _language_instruction(language)

    if target_seconds <= 59:
        structure = (
            f"Structure: a tight hook, then {facts_min}–{facts_max} very concise spoken facts "
            "(each fact short enough for the total to fit the time budget), then a brief ending."
        )
    elif target_seconds <= 120:
        structure = (
            f"Structure: a strong hook, {facts_min}–{facts_max} memorable facts with light "
            "transitions, then an ending that is either a clear call to action OR a tight summary."
        )
    else:
        structure = (
            f"Structure: a compelling hook, then {facts_min}–{facts_max} substantive facts or "
            "mini-sections (each developed enough to fill the runtime), with smooth bridges, "
            "then a satisfying closing."
        )

    system = (
        "You write engaging educational voiceover scripts for video. "
        f"The narration must be paced to fill roughly {target_seconds} seconds when read aloud "
        f"(target about {w_lo}–{w_hi} words total in the chosen language; adjust for natural speech). "
        f"{structure} "
        "Keep sentences speakable; avoid lists of numbers unless essential. "
        "full_script_plain must be the exact text to send to a TTS engine: concatenate hook, "
        "then each fact with brief transitions, then the ending. Use double newlines between "
        "major sections for natural pauses. "
        "visual_segments_en must have exactly (2 + number of facts) entries, in order: "
        "one English-only scene description for the hook, one per fact, one for the ending. "
        "Use plain ASCII/Latin English for image generation (no Devanagari, no Hindi/Marathi script). "
        "Each line should be a short, concrete visual scene (who/what/where), not narration text."
    )
    user = (
        f"Topic: {topic.strip()}\n"
        f"{lang_line}\n"
        f"Target spoken length: about {target_seconds} seconds (~{w_lo}–{w_hi} words)."
    )
    return system, user


async def generate_script(
    settings: Settings,
    topic: str,
    language: LanguageCode,
    *,
    target_duration_seconds: int = 59,
    conversational: bool = False,
) -> ScriptPayload:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
    )

    if conversational:
        t_min, t_max = _conversational_turn_bounds(target_duration_seconds)
        json_schema = _build_conversational_script_json_schema(t_min, t_max)
        system, user = _build_conversational_prompts(
            topic, language, target_duration_seconds, t_min, t_max
        )
    else:
        facts_min, facts_max = _facts_bounds(target_duration_seconds)
        json_schema = _build_script_json_schema(facts_min, facts_max)
        system, user = _build_prompts(topic, language, target_duration_seconds, facts_min, facts_max)

    try:
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": json_schema,
            },
        )
    except (APITimeoutError, RateLimitError, APIError) as e:
        logger.exception("OpenAI script generation failed: %s", e)
        raise RuntimeError("Script generation service unavailable") from e

    raw = completion.choices[0].message.content
    if not raw:
        raise RuntimeError("Empty response from OpenAI")

    data = json.loads(raw)
    if conversational:
        return _payload_from_conversational_dict(data)
    return ScriptPayload.model_validate(data)
