from __future__ import annotations


class ValidationError(ValueError):
    pass


def validate_collection_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValidationError("Collection name cannot be empty")
    if len(name) > 200:
        raise ValidationError("Collection name must be at most 200 characters")
    if len(name) < 1:
        raise ValidationError("Collection name must be at least 1 character")
    return name


def validate_document_title(title: str) -> str:
    title = title.strip()
    if not title:
        raise ValidationError("Document title cannot be empty")
    if len(title) > 500:
        raise ValidationError("Document title must be at most 500 characters")
    return title


def validate_tags(tags: list[str] | None) -> list[str]:
    if tags is None:
        return []
    cleaned = []
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if len(t) > 50:
            raise ValidationError(f"Tag '{t}' is too long (max 50 characters)")
        cleaned.append(t)
    if len(cleaned) > 50:
        raise ValidationError("Maximum 50 tags allowed")
    return cleaned
