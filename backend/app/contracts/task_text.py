"""The one rule for a task instruction that may be sent to an agent.

Every entry point that accepts a task to send (campaign and run-plan requests, and
the task recorded in an imported regression bundle) applies this rule, and the
dashboard applies the same rule in frontend/src/taskText.ts, so both sides count the
same unit and refuse the same blank tasks:

* Length is counted in Unicode code points: Python's ``len`` and JavaScript's
  ``Array.from(text).length``. (JavaScript's ``text.length`` counts UTF-16 units,
  which differ for characters such as emoji.)
* At least one character must be visible: a letter, digit, punctuation mark, symbol
  or spacing combining mark. Whitespace, line breaks, control characters, zero-width
  and other format characters (including the byte-order mark), unassigned code
  points, lone surrogates and letters that render as blank space do not count.

The text itself is never trimmed or rewritten; a task is either accepted exactly as
written or refused.
"""
import unicodedata

TASK_TEXT_MAX_CHARACTERS = 2000
# Assigned letters/symbols that render as empty space: the Hangul fillers and the
# blank Braille pattern.
BLANK_RENDERING = frozenset('ᅟᅠㅤﾠ⠀')


def visible_character(character: str) -> bool:
    category = unicodedata.category(character)
    return (category[0] in 'LNPS' or category == 'Mc') and character not in BLANK_RENDERING


def task_text_problem(text) -> str | None:
    """Why ``text`` cannot be sent to an agent as a task instruction, or None."""
    if not isinstance(text, str) or not text:
        return 'The task instruction is empty.'
    if len(text) > TASK_TEXT_MAX_CHARACTERS:
        return (f'The task instruction has {len(text)} characters; '
                f'at most {TASK_TEXT_MAX_CHARACTERS} are allowed.')
    if not any(visible_character(character) for character in text):
        return ('The task instruction has no visible character: it contains only spaces, line breaks, '
                'zero-width or other invisible characters.')
    return None


def require_sendable_task_text(text: str) -> str:
    """Pydantic after-validator: accept the exact text or refuse it; never rewrite it."""
    problem = task_text_problem(text)
    if problem:
        raise ValueError(problem)
    return text
