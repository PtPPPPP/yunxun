"""分页工具。

把“解析页码参数 + 边界裁剪 + 组装分页视图”的零散逻辑收口到这里，避免
在路由和仓储层各自手写 ``offset``/``limit`` 计算。解析阶段刻意允许“未
请求分页”（返回 ``None``），这样调用方保持原有“一次返回全部”的行为，
只有显式传参时才走分页路径，对前端完全向后兼容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Any
import base64
import json


@dataclass(frozen=True)
class PageParams:
    page: int  # 从 1 开始
    page_size: int

    @property
    def offset(self) -> int:
        return max(0, (self.page - 1) * self.page_size)

    @property
    def limit(self) -> int:
        return self.page_size


@dataclass(frozen=True)
class Page:
    items: list[Any]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size else 0

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    def to_payload(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "total_pages": self.total_pages,
            "has_prev": self.has_prev,
            "has_next": self.has_next,
        }


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("分页参数必须是整数。")


def parse_page_params(
    raw_page: str | None,
    raw_page_size: str | None,
    *,
    default_page_size: int,
    max_page_size: int,
) -> PageParams | None:
    """返回 ``None`` 表示调用方未请求分页。

    任意一个参数缺失即视为“不分页”，保持与历史接口一致；只要显式给了
    ``page``，就会按 ``default_page_size``（或显式 ``page_size``）分页。
    """
    page = _to_int(raw_page)
    page_size = _to_int(raw_page_size)
    if page is None and page_size is None:
        return None

    resolved_page = page if page is not None else 1
    resolved_size = page_size if page_size is not None else default_page_size

    if resolved_page < 1:
        raise ValueError("page 不能小于 1。")
    if resolved_size < 1:
        raise ValueError("page_size 不能小于 1。")
    if resolved_size > max_page_size:
        raise ValueError(f"page_size 不能大于 {max_page_size}。")

    return PageParams(page=resolved_page, page_size=resolved_size)


def build_page(items: Iterable[Any], total: int, params: PageParams) -> Page:
    """把已切好片的 ``items`` 组装成 :class:`Page`。"""
    return Page(items=list(items), page=params.page, page_size=params.page_size, total=total)


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
