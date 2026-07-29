"""Shared language and terminology rules for LarpManager translations."""

TONE_CONVENTIONS = """Use informal language and the second-person singular (you).
LarpManager UI strings are for event organizers and players: keep the tone
informal-professional and natural, never bureaucratic."""

LARP_TERMS = """Specific LARP terms:
- Award refers to awarding XP (Italian: "assegnazioni").
- Badges are achievements.
- Characters usually means game characters, though it can mean text characters.
- Casting is assigning characters or roles to players/participants.
- Pools are character/resource pools.
- Plot is a quest, mission, or storyline.
- Handout is setting/world-building knowledge.
- Keep "Safety" and "Speed larp" in English.
- Collection is money collection by friends.
- Matchmaker is the character-to-player matching algorithm.
- Ensemble shows the characters ensemble/cast.
- Quest and Trait are LARP terms."""


def translation_context() -> str:
    """Return the prompt fragment used by translation and translation review."""
    return f"{TONE_CONVENTIONS}\n\n{LARP_TERMS}"
