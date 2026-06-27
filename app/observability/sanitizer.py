"""日志脱敏工具。

本文件集中处理结构化日志和 LLM 日志的敏感信息脱敏，避免 API key、
Authorization token、密码等内容进入 stdout 或数据库日志。
"""

import re
from typing import Any

SENSITIVE_KEYWORDS = ("api_key", "apikey", "authorization", "token", "secret", "password")
REDACTED = "[REDACTED]"

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{12,}", re.IGNORECASE),
    re.compile(r"(AUTHORIZATION)\s*=\s*Bearer\s+[A-Za-z0-9_\-\.]{12,}", re.IGNORECASE),
    re.compile(
        r"((?:OPENAI_)?API_KEY|AUTHORIZATION|TOKEN|SECRET|PASSWORD)\s*=\s*[^\s,;]+",
        re.IGNORECASE,
    ),
]


def sanitize_for_logging(value: Any) -> Any:
    """递归脱敏可 JSON 序列化日志对象中的敏感字段和值。"""
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = sanitize_for_logging(item)
        return sanitized

    if isinstance(value, list):
        return [sanitize_for_logging(item) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitize_for_logging(item) for item in value)

    if isinstance(value, str):
        return _sanitize_text(value)

    return value


def _is_sensitive_key(key: str) -> bool:
    """判断字段名是否属于敏感信息。"""
    normalized = key.lower().replace("-", "_")
    return any(keyword in normalized for keyword in SENSITIVE_KEYWORDS)


def _sanitize_text(text: str) -> str:
    """脱敏字符串中的常见 key/token 片段。"""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            sanitized = pattern.sub(lambda match: f"{match.group(1)}={REDACTED}", sanitized)
        else:
            sanitized = pattern.sub(REDACTED, sanitized)
    return sanitized
