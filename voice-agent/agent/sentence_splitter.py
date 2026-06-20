"""Sentence boundary detection for streaming TTS pipeline."""

_MIN_SENTENCE_LENGTH = 12
_SENTENCE_ENDINGS = '.!?…'
_CLAUSE_SEPARATORS = ',;:'


def find_sentence_boundary(buffer: str) -> tuple[str, str]:
    """Split buffer at the first sentence boundary, if one exists.

    Returns (sentence, remainder). If no boundary is found or the sentence
    would be shorter than MIN_SENTENCE_LENGTH, returns ("", buffer) to
    indicate no split should happen yet.

    Splitting priorities:
    1. Sentence endings (.!?…) after MIN_SENTENCE_LENGTH chars
    2. Clause separators (,;:) after 30 chars (avoids waiting too long)
    3. Newline boundaries
    """
    if len(buffer) < _MIN_SENTENCE_LENGTH:
        return "", buffer

    # Check for newline as sentence boundary first (e.g. bullet lists)
    newline_idx = buffer.find('\n', _MIN_SENTENCE_LENGTH)
    if newline_idx > 0:
        sentence = buffer[:newline_idx].strip()
        remainder = buffer[newline_idx + 1:].lstrip()
        if sentence:
            return sentence, remainder

    for i in range(_MIN_SENTENCE_LENGTH - 1, len(buffer)):
        if buffer[i] in _SENTENCE_ENDINGS:
            if buffer[i] == '.' and i > 0 and buffer[i - 1].isdigit():
                continue
            is_end = (i == len(buffer) - 1) or buffer[i + 1] in ' \n\r'
            if is_end:
                sentence = buffer[:i + 1].strip()
                remainder = buffer[i + 1:].lstrip()
                return sentence, remainder

    # Fallback: split on clause separators if buffer grows too long (>30 chars)
    if len(buffer) > 30:
        for i in range(30, len(buffer)):
            if buffer[i] in _CLAUSE_SEPARATORS:
                is_end = (i == len(buffer) - 1) or buffer[i + 1] in ' \n\r'
                if is_end:
                    sentence = buffer[:i + 1].strip()
                    remainder = buffer[i + 1:].lstrip()
                    return sentence, remainder

    return "", buffer
