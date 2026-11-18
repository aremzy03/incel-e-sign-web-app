"""
One set of rules for field payloads, shared by envelope create/update,
self-sign and the per-envelope fields endpoint.
"""

from __future__ import annotations

from rest_framework import serializers

from .stamps import DATE_FORMATS

# Types that may be created. "text" is retired: free text is added to the PDF
# with Add text instead. Existing text fields keep rendering.
CREATABLE_FIELD_TYPES = frozenset({"initials", "date", "designation"})
RETIRED_FIELD_TYPES = frozenset({"text"})
# The server fills these at signing time; any client-supplied value is ignored.
SERVER_FILLED_FIELD_TYPES = frozenset({"initials", "date"})

TEXT_RETIRED_MESSAGE = "Text fields are no longer supported. Use Add text to put text on the document."


def validate_field_type(typ: object, prefix: str = "") -> str:
    typ = str(typ)
    if typ in RETIRED_FIELD_TYPES:
        raise serializers.ValidationError(f"{prefix}{TEXT_RETIRED_MESSAGE}")
    if typ not in CREATABLE_FIELD_TYPES:
        raise serializers.ValidationError(
            f"{prefix}type must be one of {sorted(CREATABLE_FIELD_TYPES)}"
        )
    return typ


def validate_date_format(date_format: object, prefix: str = "") -> None:
    if date_format in (None, ""):
        return
    if date_format not in DATE_FORMATS:
        raise serializers.ValidationError(
            f"{prefix}date_format must be one of {list(DATE_FORMATS)}"
        )


def validate_field_item(
    item: object,
    index: int,
    *,
    document_ids: set[str],
    required_keys: tuple[str, ...],
    require_value_when_required: bool = False,
) -> None:
    """Validate one field dict from an envelope or self-sign payload."""
    prefix = f"fields[{index}]."
    if not isinstance(item, dict):
        raise serializers.ValidationError(f"fields[{index}] must be an object")

    missing = [k for k in required_keys if k not in item]
    if missing:
        raise serializers.ValidationError(f"fields[{index}] missing keys: {missing}")

    doc_id = str(item.get("document_id"))
    if doc_id not in document_ids:
        raise serializers.ValidationError(f"{prefix}document_id {doc_id} not in document_ids")

    typ = validate_field_type(item.get("type"), prefix)

    try:
        page = int(item.get("page"))
        x = float(item.get("x"))
        y = float(item.get("y"))
        width = float(item.get("width"))
        height = float(item.get("height"))
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError(f"fields[{index}] numeric fields must be numbers") from exc
    if page < 1 or x < 0 or y < 0 or width < 0 or height < 0:
        raise serializers.ValidationError(
            f"fields[{index}] invalid coordinates: page>=1; x,y,width,height>=0"
        )

    if typ == "designation":
        max_length = item.get("max_length")
        if max_length is not None and int(max_length) <= 0:
            raise serializers.ValidationError(f"{prefix}max_length must be positive when provided")

    if typ == "date":
        validate_date_format(item.get("date_format"), prefix)

    if require_value_when_required and typ not in SERVER_FILLED_FIELD_TYPES and bool(item.get("required")):
        if item.get("value") in (None, "") and item.get("prefill_value") in (None, ""):
            raise serializers.ValidationError(
                f"fields[{index}] requires value or prefill_value when required=true"
            )


def clean_field_values(item: dict) -> dict:
    """Drop client-supplied values for fields the server fills at signing time."""
    if str(item.get("type")) in SERVER_FILLED_FIELD_TYPES:
        item = {**item, "value": None, "prefill_value": None}
    return item
