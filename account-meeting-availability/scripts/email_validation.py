#!/usr/bin/env python3
"""Practical, dependency-free validation for stored contact email addresses."""

from __future__ import annotations

import re


LOCAL_PART_RE = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+")
DOMAIN_LABEL_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def validate_practical_email(value: str | None, *, allow_blank: bool = False) -> str:
    """Return a trimmed ASCII mailbox address or raise ``ValueError``.

    This deliberately supports the common dot-atom/domain form used by Outlook
    contacts. Display names, comments, quoted local parts, address literals, and
    local-only domains are rejected so ambiguous recipient data fails closed.
    """

    if value is None:
        email = ""
    elif not isinstance(value, str):
        raise ValueError("email address must be a string")
    else:
        email = value.strip()
    if not email:
        if allow_blank:
            return ""
        raise ValueError("email address is required")

    if len(email) > 254:
        raise ValueError("email address exceeds 254 characters")
    if any(ord(character) < 33 or ord(character) > 126 for character in email):
        raise ValueError("email address must contain printable ASCII characters without spaces")
    if email.count("@") != 1:
        raise ValueError("email address must contain exactly one '@'")

    local_part, domain = email.rsplit("@", 1)
    if not local_part or len(local_part) > 64:
        raise ValueError("email local part must contain 1 to 64 characters")
    if local_part.startswith(".") or local_part.endswith(".") or ".." in local_part:
        raise ValueError("email local part cannot start/end with '.' or contain consecutive dots")
    if not LOCAL_PART_RE.fullmatch(local_part):
        raise ValueError("email local part contains unsupported characters")

    if len(domain) > 253 or domain.startswith(".") or domain.endswith("."):
        raise ValueError("email domain is malformed")
    labels = domain.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2:
        raise ValueError("email domain must be a fully qualified domain name")
    if any(not DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise ValueError("email domain contains an invalid label")

    return email
