"""Мелкие форматтеры, общие для нескольких виджетов."""


def format_size(n) -> str:
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
    