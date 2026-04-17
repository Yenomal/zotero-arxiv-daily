import re


def _truncate_plain_text(text: str, headings: list[str]) -> str:
    lines = text.splitlines()
    cutoff = len(lines)
    heading_set = {heading.lower() for heading in headings}

    for index, line in enumerate(lines):
        normalized = re.sub(r'[#*:>\-\s]+', ' ', line).strip().lower()
        if normalized in heading_set:
            cutoff = index
            break

    cleaned = "\n".join(lines[:cutoff]).strip()
    return cleaned or text.strip()


def _truncate_tex_text(text: str, headings: list[str]) -> str:
    patterns = [
        r'\\bibliography\{',
        r'\\begin\{thebibliography\}',
    ]
    for heading in headings:
        escaped = re.escape(heading)
        patterns.append(rf'\\section\*?\{{\s*{escaped}\s*\}}')
        patterns.append(rf'\\chapter\*?\{{\s*{escaped}\s*\}}')

    cutoff = len(text)
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            cutoff = min(cutoff, match.start())

    cleaned = text[:cutoff].strip()
    return cleaned or text.strip()


def clean_full_text(text: str | None, text_source: str | None, headings: list[str]) -> str | None:
    if not text:
        return None

    if text_source == "tar":
        return _truncate_tex_text(text, headings)

    return _truncate_plain_text(text, headings)
