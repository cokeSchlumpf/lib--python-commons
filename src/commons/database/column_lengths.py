"""Shared ``max_length`` bounds for String columns.

Unbounded ``str`` columns map to an open-ended String, which some databases realise
as a very large / max-width text type (and which can't sit in an index on SQL Server).
Every String column in this package picks a bound from here; genuinely long free text
(e.g. description bodies) uses an explicit ``Text`` type instead of a cap.
"""

# uuid-string surrogate keys (our ids are 36-char uuid4 strings)
ID_LENGTH = 36
# short business codes (e.g. a manual or country code)
CODE_LENGTH = 64
# names, titles, display names, and external identifiers we don't control the width of
NAME_LENGTH = 255
# Literal-valued columns stored as String (status / kind / mode / license enums)
ENUM_LENGTH = 64
