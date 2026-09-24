"""Prompt sanitizer for Google Flow video generation.

Sanitizes prompt text to bypass false-positive triggers in Google Flow's AI safety
filters (especially child/infant/harm/suffocation words found in dramatic scripts/lakorn).
"""
import re

SAFETY_TRIGGERS = [
    'mother', 'baby', 'infant', 'child', 'bassinet', 'cradle',
    'cloth', 'press', 'smother', 'cover', 'tiny', 'figurine'
]


def sanitize_lakorn_prompt(raw_prompt: str) -> str:
    """Sanitize prompt text to pass Google Flow Safety Filters.

    Removes boilerplate headers, negative prompts, and sensitive actions/words
    ('mother', 'bassinets', 'infant', 'cloth onto figurine') that trigger AI
    child/harm safety classifiers, ensuring safe, high-aesthetic cinematic motion.
    """
    if not raw_prompt or not raw_prompt.strip():
        return "Slow cinematic motion of the glass statues in the room, dramatic atmospheric lighting"

    # If any sensitive words exist that could trigger the zero-tolerance safety classifier
    if any(re.search(rf'\b{w}\b', raw_prompt, re.I) for w in SAFETY_TRIGGERS):
        return "Slow cinematic motion of the glass statues in the room, dramatic atmospheric lighting"

    lines = [line.strip() for line in raw_prompt.splitlines() if line.strip()]
    content_lines = [l for l in lines if not re.match(r'^(Episode|Scene)\s*:', l, re.I)]
    clean_lines = [l for l in content_lines if not l.lower().startswith('no ')]
    text = " ".join(clean_lines).strip()

    return text or "Slow cinematic motion of the glass statues in the room, dramatic atmospheric lighting"
