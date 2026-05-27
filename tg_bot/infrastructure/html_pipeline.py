import re
from typing import Optional


def prepare_html_for_telegram(text: Optional[str]) -> str:
    """Unified HTML sanitization pipeline for Telegram (manifest §2.2)."""
    if not text:
        return ""

    # 1. Remove Markdown Code Blocks
    text = re.sub(r'```(?:html|text|md|xml)?\n?', '', text, flags=re.IGNORECASE)
    text = text.replace('```', '')

    # 2. Dangerous Protocols In Href/src/action
    text = re.sub(
        r'(?:href|src|action)\s*=\s*["\']?(?:javascript|data|vbscript):[^"\'\s]*["\']?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\s+href\s*=\s*["\']//[^"\'\s]*["\']?', '', text, flags=re.IGNORECASE)

    # 3. Dangerous Tags (remove Opening And Closing Tags With Content)
    dangerous = (
        r'(?:script|iframe|style|form|meta|base|svg|img|input|textarea|select|keygen|video|audio|object|embed|link)'
    )
    # Remove Entire Tags With Content (opening Tag + Content + Closing Tag)
    text = re.sub(rf'<{dangerous}\b[^>]*>.*?</{dangerous}>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove Self-closing Dangerous Tags
    text = re.sub(rf'<{dangerous}\b[^>]*/>', '', text, flags=re.IGNORECASE)
    # Remove Remaining Opening Tags
    text = re.sub(rf'<{dangerous}\b[^>]*>', '', text, flags=re.IGNORECASE)
    # Remove Remaining Closing Tags
    text = re.sub(rf'</{dangerous}>', '', text, flags=re.IGNORECASE)

    # 4. Event Handlers On*
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', text, flags=re.IGNORECASE)

    # 5. Markdown → HTML
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # 6. List Artifacts
    text = re.sub(r'^\s*[\-•\d\.]+\s*', '', text, flags=re.MULTILINE)

    # 7. Normalize Quotes In Attributes
    text = re.sub(r"(href|src|action)(\s*=\s*)'([^']*)'", r'\1\2"\3"', text, flags=re.IGNORECASE)

    # 8. Close Unclosed Tags
    for tag in ("b", "i", "u", "code", "a"):
        open_c = text.count(f"<{tag}>")
        close_c = text.count(f"</{tag}>")
        if open_c > close_c:
            text += f"</{tag}>" * (open_c - close_c)

    return text.strip()

