"""Display-name validation. Names never determine authorization or identity."""
import unicodedata


def preferred_name(value: str) -> str:
    value = unicodedata.normalize('NFC', ' '.join(value.split()))
    if not 1 <= len(value) <= 60 or not any(c.isalpha() for c in value) or any(
        not (c.isalpha() or c.isspace() or c in "'-.") for c in value
    ):
        raise ValueError('Enter a name of 1–60 characters using letters, spaces, apostrophes, periods or hyphens.')
    return value
