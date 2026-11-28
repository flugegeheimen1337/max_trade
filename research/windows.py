"""Chronological research windows. The holdout is never used for tuning."""

from __future__ import annotations

from datetime import date, timedelta


def split_windows(start: date, end: date, split: dict[str, float]) -> dict[str, str]:
    total = (end - start).days
    if total <= 0:
        raise ValueError("The research period is empty.")
    if abs(sum(split.values()) - 1.0) > 1e-9:
        raise ValueError("Split fractions must add up to 1.")
    dev_end = start + timedelta(days=round(total * split["development"]))
    val_end = dev_end + timedelta(days=round(total * split["validation"]))
    fmt = "%Y%m%d"
    return {
        "development": f"{start.strftime(fmt)}-{dev_end.strftime(fmt)}",
        "validation": f"{dev_end.strftime(fmt)}-{val_end.strftime(fmt)}",
        "holdout": f"{val_end.strftime(fmt)}-{end.strftime(fmt)}",
    }
