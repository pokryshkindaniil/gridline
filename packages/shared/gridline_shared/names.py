"""Name normalisation for identity matching.

`normalize_name` produces the *comparison key* of a source spelling. It is deliberately conservative:

  - Unicode is composed (NFKC) and case-folded, so "STRASSE" and "straße" compare equal;
  - runs of whitespace and punctuation (spaces, hyphens, dots, apostrophes, slashes, brackets) become one space,
    so "Mercedes - AMG Team" and "Mercedes-AMG Team" compare equal;
  - accents are KEPT ("Müller" != "Muller"): dropping them can join two different people, and the slug (which does
    fold accents) is the only place that is accepted;
  - nothing fuzzy happens here: no nicknames, no transliteration, no edit distance, no word re-ordering.

The original spelling is never replaced by this key; it is stored next to it as provenance.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return _SEPARATORS.sub(" ", text).strip()
