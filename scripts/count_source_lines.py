from __future__ import annotations

import argparse
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_LINES = 1750
EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}
BACKEND_EXTENSIONS = {".py"}
FRONTEND_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".css"}


@dataclass(frozen=True)
class FileLineCount:
    path: Path
    lines: int


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def iter_source_files(base_dir: Path, extensions: set[str]) -> list[Path]:
    if not base_dir.exists():
        return []

    files: list[Path] = []
    for path in base_dir.rglob("*"):
        if path.is_file() and path.suffix in extensions and not is_excluded(path.relative_to(PROJECT_ROOT)):
            files.append(path)
    return sorted(files)


def count_python_lines(source: str) -> int:
    code_lines: set[int] = set()
    token_stream = tokenize.generate_tokens(io.StringIO(source).readline)

    for token in token_stream:
        token_type = token.type
        if token_type in {
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
            tokenize.ENCODING,
        }:
            continue

        start_line, _ = token.start
        end_line, _ = token.end
        for line_number in range(start_line, end_line + 1):
            if source.splitlines()[line_number - 1].strip():
                code_lines.add(line_number)

    return len(code_lines)


def count_c_like_lines(source: str) -> int:
    code_lines = 0
    in_block_comment = False
    in_string: str | None = None
    escape_next = False

    for line in source.splitlines():
        has_code = False
        index = 0

        while index < len(line):
            current = line[index]
            next_char = line[index + 1] if index + 1 < len(line) else ""

            if in_block_comment:
                if current == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue

            if in_string:
                has_code = True
                if escape_next:
                    escape_next = False
                elif current == "\\":
                    escape_next = True
                elif current == in_string:
                    in_string = None
                index += 1
                continue

            if current == "/" and next_char == "/":
                break
            if current == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if current in {"'", '"', "`"}:
                in_string = current
                has_code = True
                index += 1
                continue
            if not current.isspace():
                has_code = True
            index += 1

        if has_code:
            code_lines += 1

    return code_lines


def count_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".py":
        return count_python_lines(source)
    return count_c_like_lines(source)


def build_report(name: str, base_dir: Path, extensions: set[str]) -> tuple[str, list[FileLineCount]]:
    files = iter_source_files(base_dir, extensions)
    counts = [FileLineCount(path=file, lines=count_file(file)) for file in files]
    return name, counts


def print_report(title: str, counts: list[FileLineCount], target: int) -> int:
    total = sum(item.lines for item in counts)
    status = "达标" if total > target else "未达标"
    print(f"\n{title}: {total} 行（{status}，目标 > {target}）")
    print("-" * 72)
    for item in sorted(counts, key=lambda current: str(current.path.relative_to(PROJECT_ROOT))):
        relative = item.path.relative_to(PROJECT_ROOT)
        print(f"{item.lines:5d}  {relative}")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="统计 yunxun 前后端有效源代码行数。")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_LINES, help="达标行数，默认 1750。")
    args = parser.parse_args()

    backend_name, backend_counts = build_report("后端", PROJECT_ROOT / "backend", BACKEND_EXTENSIONS)
    frontend_name, frontend_counts = build_report("前端", PROJECT_ROOT / "frontend" / "src", FRONTEND_EXTENSIONS)

    backend_total = print_report(backend_name, backend_counts, args.target)
    frontend_total = print_report(frontend_name, frontend_counts, args.target)
    combined_total = backend_total + frontend_total

    print("\n汇总")
    print("-" * 72)
    print(f"后端有效代码：{backend_total} 行，{'是' if backend_total > args.target else '否'}超过 {args.target}")
    print(f"前端有效代码：{frontend_total} 行，{'是' if frontend_total > args.target else '否'}超过 {args.target}")
    print(f"总计：{combined_total} 行")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
