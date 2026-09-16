"""分页工具。

列表接口统一使用基于游标（cursor）的翻页方式：把上一页最后一条记录的
``(created_at, id)`` 编码成一个不透明字符串交给客户端，下一页请求带回来
即可继续向后读取。相比页码分页，游标分页在数据持续写入时不会出现重复或
漏读。
"""

from __future__ import annotations

import base64
import json


def encode_cursor(created_at: str, item_id: str) -> str:
    raw = json.dumps([created_at, item_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        created_at, item_id = json.loads(raw)
        if not isinstance(created_at, str) or not isinstance(item_id, str) or not created_at or not item_id:
            raise ValueError
        return created_at, item_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor 无效。") from exc
