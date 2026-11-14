"""从 source-code.txt 重新生成软著源码材料 docx。

修正原 docx 的格式问题：原版把每一页的 50 行代码塞进同一个段落、用软换行
（<w:br/>）连接，导致：
  1. 不同源文件的代码在 Word 里视觉上"糊成一团"（如 `import socketimport sys`）；
  2. 整页代码是一个逻辑段落，无法按行操作，长代码行自动折行与软换行混淆。

本脚本改为每一行代码独立成一个段落，页眉单独一段，并保留原版的全部样式：
  - 页面：A4（7560310 × 10692130 EMU），边距上下 411480 / 左右 502920 EMU
  - 页眉：宋体（SimSun）10.5pt 加粗、居中、段后 3pt
  - 代码：Consolas 7.5pt（东亚回退宋体）、行距固定 8.5pt、段前段后 0
  - 分页：每个新页面的页眉段设置 page_break_before
  - 内容：与 source-code.txt 逐行 100% 一致（184 页，每页 1 行页眉 + 50 行正文）

用法：
  python scripts/generate_source_docx.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_TXT = (
    PROJECT_ROOT
    / "docs"
    / "software-copyright"
    / "current-draft-2026-10-19"
    / "source-code"
    / "source-code.txt"
)
OUTPUT_DOCX = (
    PROJECT_ROOT
    / "docs"
    / "software-copyright"
    / "current-draft-2026-10-19"
    / "source-code"
    / "yunxun-project-source-code-current.docx"
)

# 与原 docx 保持一致的几何量（EMU）
PAGE_WIDTH = Emu(7560310)
PAGE_HEIGHT = Emu(10692130)
MARGIN_TOP_BOTTOM = Emu(411480)
MARGIN_LEFT_RIGHT = Emu(502920)

HEADER_FONT = "宋体"
HEADER_SIZE = Pt(10.5)
CODE_FONT = "Consolas"
CODE_EAST_ASIA_FONT = "宋体"
CODE_SIZE = Pt(7.5)
CODE_LINE_SPACING = Pt(8.5)


def set_run_font(run, ascii_font: str, east_asia_font: str, size, bold: bool) -> None:
    run.font.name = ascii_font
    run.font.size = size
    run.font.bold = bold
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), ascii_font)
    r_fonts.set(qn("w:hAnsi"), ascii_font)
    r_fonts.set(qn("w:eastAsia"), east_asia_font)


def add_header_paragraph(doc: Document, text: str, page_break_before: bool) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(3)
    if page_break_before:
        p.paragraph_format.page_break_before = True
    run = p.add_run(text)
    set_run_font(run, HEADER_FONT, HEADER_FONT, HEADER_SIZE, bold=True)


def add_code_paragraph(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = CODE_LINE_SPACING
    run = p.add_run(text)
    set_run_font(run, CODE_FONT, CODE_EAST_ASIA_FONT, CODE_SIZE, bold=False)


def main() -> int:
    raw = SOURCE_TXT.read_text(encoding="utf-8").rstrip("\n")
    pages = raw.split("\n\f\n")

    doc = Document()

    # 页面设置
    section = doc.sections[0]
    section.page_width = PAGE_WIDTH
    section.page_height = PAGE_HEIGHT
    section.top_margin = MARGIN_TOP_BOTTOM
    section.bottom_margin = MARGIN_TOP_BOTTOM
    section.left_margin = MARGIN_LEFT_RIGHT
    section.right_margin = MARGIN_LEFT_RIGHT

    # Normal 样式默认字体（代码用）
    normal = doc.styles["Normal"]
    normal.font.name = CODE_FONT
    normal.font.size = CODE_SIZE
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CODE_EAST_ASIA_FONT)

    for page_index, page in enumerate(pages):
        lines = page.split("\n")
        header = lines[0]
        body = lines[1:]
        add_header_paragraph(doc, header, page_break_before=(page_index > 0))
        for line in body:
            add_code_paragraph(doc, line)

    OUTPUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT_DOCX)
    print(f"已生成：{OUTPUT_DOCX}")
    print(f"页面数：{len(pages)}")
    total_body = sum(len(page.split(chr(10))) - 1 for page in pages)
    print(f"正文行数：{total_body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
