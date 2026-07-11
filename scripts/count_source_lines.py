from __future__ import annotations

import argparse
import io
import math
import tokenize
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOFTWARE_FULL_NAME = "云寻智慧农业AI工作台软件"
SOFTWARE_SHORT_NAME = "云寻AI"
SOFTWARE_VERSION = "V4.0"
LINES_PER_PAGE = 50
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "software-copyright"

BACKEND_EXTENSIONS = {".py"}
FRONTEND_CODE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
STYLE_EXTENSIONS = {".css"}
FRONTEND_EXTENSIONS = FRONTEND_CODE_EXTENSIONS | STYLE_EXTENSIONS

EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "__tests__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "test",
    "tests",
    "venv",
}
EXCLUDED_FILENAMES = {
    "package-lock.json",
    "vite.config.d.ts",
    "vite.config.js",
}
EXCLUDED_SUFFIXES = {
    ".d.ts",
    ".log",
    ".pyc",
    ".pyo",
    ".spec.ts",
    ".spec.tsx",
    ".test.ts",
    ".test.tsx",
}
EXCLUSION_DESCRIPTIONS = (
    "依赖与锁文件：node_modules、package-lock.json",
    "测试代码：tests、test、__tests__、test_*.py、*_test.py、*.test.*、*.spec.*",
    "构建与缓存：dist、build、coverage、__pycache__、pytest/mypy/ruff 缓存",
    "环境与工具：.git、虚拟环境、IDE 配置、日志、数据库、上传数据和大型静态资源",
    "自动生成与声明文件：*.d.ts、vite.config.js、vite.config.d.ts",
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    category: str
    lines: tuple[str, ...]

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(PROJECT_ROOT)

    @property
    def line_count(self) -> int:
        return len(self.lines)


@dataclass(frozen=True)
class SourceStatistics:
    file_count: int
    backend_lines: int
    frontend_lines: int
    style_lines: int
    total_lines: int
    total_pages: int


def is_test_file(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or any(name.endswith(suffix) for suffix in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def is_excluded(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT)
    parts = {part.casefold() for part in relative.parts}
    name = path.name.casefold()
    return (
        bool(parts & EXCLUDED_DIRS)
        or name in EXCLUDED_FILENAMES
        or any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)
        or is_test_file(path)
    )


def category_for_path(path: Path) -> str:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    if relative == "backend/main.py":
        return "后端入口"
    if relative == "backend/app/main.py":
        return "后端应用入口"
    if relative.startswith("backend/app/api/"):
        return "后端 API"
    if relative.startswith("backend/app/services/"):
        return "后端业务逻辑"
    if relative == "backend/app/schemas.py":
        return "后端数据模型"
    if relative == "backend/app/repositories.py":
        return "后端数据访问"
    if relative.startswith("backend/app/core/"):
        return "后端核心工具"
    if relative.startswith("backend/"):
        return "后端其他源码"
    if relative == "frontend/src/main.tsx":
        return "前端入口"
    if relative == "frontend/src/App.tsx":
        return "前端主页面"
    if "/pages/" in relative or "/routes/" in relative:
        return "前端页面与路由"
    if "/components/" in relative:
        return "前端组件"
    if "/hooks/" in relative:
        return "前端 Hooks"
    if "/services/" in relative or "/lib/api" in relative:
        return "前端服务与 API"
    if "/stores/" in relative or "/state/" in relative:
        return "前端状态管理"
    if "/utils/" in relative or "/lib/" in relative:
        return "前端工具"
    if path.suffix.casefold() in STYLE_EXTENSIONS:
        return "前端核心样式"
    return "前端其他源码"


CATEGORY_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "后端入口",
            "后端应用入口",
            "后端 API",
            "后端业务逻辑",
            "后端数据模型",
            "后端数据访问",
            "后端核心工具",
            "后端其他源码",
            "前端入口",
            "前端主页面",
            "前端页面与路由",
            "前端组件",
            "前端 Hooks",
            "前端服务与 API",
            "前端状态管理",
            "前端工具",
            "前端其他源码",
            "前端核心样式",
        )
    )
}


def source_sort_key(path: Path) -> tuple[int, str]:
    category = category_for_path(path)
    relative = path.relative_to(PROJECT_ROOT).as_posix().casefold()
    return CATEGORY_ORDER[category], relative


def iter_source_paths() -> list[Path]:
    candidates = [
        *(PROJECT_ROOT / "backend").rglob("*.py"),
        *(
            path
            for path in (PROJECT_ROOT / "frontend" / "src").rglob("*")
            if path.is_file() and path.suffix.casefold() in FRONTEND_EXTENSIONS
        ),
    ]
    return sorted((path for path in candidates if path.is_file() and not is_excluded(path)), key=source_sort_key)


def python_source_lines(source: str) -> tuple[str, ...]:
    physical_lines = source.splitlines()
    code_line_numbers: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type in {
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
                tokenize.ENCODING,
            }:
                continue
            for line_number in range(token.start[0], token.end[0] + 1):
                if physical_lines[line_number - 1].strip():
                    code_line_numbers.add(line_number)
    except (IndentationError, tokenize.TokenError) as exc:
        raise ValueError(f"无法解析 Python 源码：{exc}") from exc
    return tuple(physical_lines[number - 1] for number in sorted(code_line_numbers))


def c_like_source_lines(source: str) -> tuple[str, ...]:
    selected: list[str] = []
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
            selected.append(line)
    return tuple(selected)


def read_source_file(path: Path) -> SourceFile:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"源码文件不是 UTF-8 编码：{path}") from exc
    lines = python_source_lines(source) if path.suffix.casefold() == ".py" else c_like_source_lines(source)
    return SourceFile(path=path, category=category_for_path(path), lines=lines)


def collect_source_files() -> list[SourceFile]:
    return [source_file for path in iter_source_paths() if (source_file := read_source_file(path)).line_count]


def calculate_statistics(source_files: list[SourceFile]) -> SourceStatistics:
    backend_lines = sum(item.line_count for item in source_files if item.relative_path.parts[0] == "backend")
    frontend_lines = sum(item.line_count for item in source_files if item.relative_path.parts[0] == "frontend")
    style_lines = sum(item.line_count for item in source_files if item.path.suffix.casefold() in STYLE_EXTENSIONS)
    total_lines = backend_lines + frontend_lines
    total_pages = math.ceil(total_lines / LINES_PER_PAGE) if total_lines else 0
    return SourceStatistics(
        file_count=len(source_files),
        backend_lines=backend_lines,
        frontend_lines=frontend_lines,
        style_lines=style_lines,
        total_lines=total_lines,
        total_pages=total_pages,
    )


def render_source_material(source_files: list[SourceFile], statistics: SourceStatistics) -> str:
    all_lines = [line for source_file in source_files for line in source_file.lines]
    pages: list[str] = []
    for page_index in range(statistics.total_pages):
        start = page_index * LINES_PER_PAGE
        body = all_lines[start : start + LINES_PER_PAGE]
        header = f"{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}    第 {page_index + 1} 页 / 共 {statistics.total_pages} 页"
        pages.append("\n".join((header, *body)))
    return "\n\f\n".join(pages) + "\n"


def render_manifest(source_files: list[SourceFile], statistics: SourceStatistics) -> str:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "软件著作权源码材料清单",
        "=" * 72,
        f"软件全称：{SOFTWARE_FULL_NAME}",
        f"软件简称：{SOFTWARE_SHORT_NAME}",
        f"版本号：{SOFTWARE_VERSION}",
        f"生成时间：{generated_at}",
        f"纳入文件数量：{statistics.file_count}",
        f"后端源码行数：{statistics.backend_lines}",
        f"前端源码行数（含样式）：{statistics.frontend_lines}",
        f"样式代码行数（前端行数的子集）：{statistics.style_lines}",
        f"有效源码总行数：{statistics.total_lines}",
        f"材料总页数：{statistics.total_pages}",
        f"分页规则：每页 {LINES_PER_PAGE} 行源码正文，页眉不计入正文行数，末页可不足 {LINES_PER_PAGE} 行。",
        "",
        "排除规则",
        "-" * 72,
        *(f"- {description}" for description in EXCLUSION_DESCRIPTIONS),
        "",
        "固定排序规则",
        "-" * 72,
        "分类顺序：后端入口 → API → 业务逻辑 → 数据模型/访问 → 核心工具 → 前端入口 → 页面/组件 → 服务/工具 → 样式。",
        "同一分类内按相对路径字典序排列；相同仓库状态下重复运行顺序一致。",
        "",
        "实际纳入文件",
        "-" * 72,
    ]
    material_line = 1
    for index, source_file in enumerate(source_files, start=1):
        end_line = material_line + source_file.line_count - 1
        relative = source_file.relative_path.as_posix()
        lines.append(
            f"{index:02d}. [{source_file.category}] {relative} | {source_file.line_count} 行 | 材料行 {material_line}-{end_line}"
        )
        material_line = end_line + 1
    return "\n".join(lines) + "\n"


def validate_source_material(content: str, statistics: SourceStatistics) -> None:
    pages = content.rstrip("\n").split("\n\f\n") if content else []
    if len(pages) != statistics.total_pages:
        raise ValueError("源码材料总页数校验失败。")
    body_line_count = 0
    for page_number, page in enumerate(pages, start=1):
        page_lines = page.splitlines()
        expected_header = f"{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}    第 {page_number} 页 / 共 {statistics.total_pages} 页"
        if not page_lines or page_lines[0] != expected_header:
            raise ValueError(f"第 {page_number} 页页眉校验失败。")
        body_lines = page_lines[1:]
        expected_count = LINES_PER_PAGE if page_number < statistics.total_pages else statistics.total_lines - body_line_count
        if len(body_lines) != expected_count:
            raise ValueError(f"第 {page_number} 页正文行数校验失败。")
        body_line_count += len(body_lines)
    if body_line_count != statistics.total_lines:
        raise ValueError("源码材料正文总行数校验失败。")


def generate_materials(output_dir: Path, source_files: list[SourceFile], statistics: SourceStatistics) -> tuple[Path, Path]:
    if not source_files:
        raise ValueError("没有找到可用于软著材料的源码文件。")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_content = render_source_material(source_files, statistics)
    validate_source_material(source_content, statistics)
    source_path = output_dir / "source-code.txt"
    manifest_path = output_dir / "source-code-manifest.txt"
    source_path.write_text(source_content, encoding="utf-8", newline="\n")
    manifest_path.write_text(render_manifest(source_files, statistics), encoding="utf-8", newline="\n")
    return source_path, manifest_path


def print_statistics(source_files: list[SourceFile], statistics: SourceStatistics) -> None:
    print(f"软件：{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}")
    print(f"纳入文件：{statistics.file_count} 个")
    print(f"后端源码：{statistics.backend_lines} 行")
    print(f"前端源码：{statistics.frontend_lines} 行（其中样式 {statistics.style_lines} 行）")
    print(f"有效源码总计：{statistics.total_lines} 行")
    print(f"按每页 {LINES_PER_PAGE} 行生成：{statistics.total_pages} 页")
    print("\n文件顺序：")
    for index, source_file in enumerate(source_files, start=1):
        print(f"{index:02d}. [{source_file.category}] {source_file.relative_path.as_posix()} ({source_file.line_count} 行)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计并生成云寻智慧农业AI工作台软件的软著源码材料。")
    parser.add_argument("--generate", action="store_true", help="生成 source-code.txt 和 source-code-manifest.txt。")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="材料输出目录。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_files = collect_source_files()
    statistics = calculate_statistics(source_files)
    print_statistics(source_files, statistics)
    if args.generate:
        source_path, manifest_path = generate_materials(args.output_dir, source_files, statistics)
        print(f"\n已生成：{source_path}")
        print(f"已生成：{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
