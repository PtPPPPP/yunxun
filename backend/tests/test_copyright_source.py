from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.count_source_lines import (
    LINES_PER_PAGE,
    SOFTWARE_FULL_NAME,
    SOFTWARE_VERSION,
    calculate_statistics,
    collect_source_files,
    generate_materials,
)


class CopyrightSourceMaterialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_files = collect_source_files()
        self.statistics = calculate_statistics(self.source_files)

    def test_discovery_is_stable_and_excludes_non_product_code(self) -> None:
        first_paths = [item.relative_path.as_posix() for item in self.source_files]
        second_paths = [item.relative_path.as_posix() for item in collect_source_files()]

        self.assertEqual(first_paths, second_paths)
        self.assertTrue(first_paths)
        self.assertFalse(any("/tests/" in f"/{path}/" for path in first_paths))
        self.assertNotIn("frontend/package-lock.json", first_paths)
        self.assertNotIn("frontend/vite.config.js", first_paths)
        self.assertNotIn("frontend/vite.config.d.ts", first_paths)

    def test_generated_material_has_valid_headers_and_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path, manifest_path = generate_materials(
                Path(temporary_directory), self.source_files, self.statistics
            )
            content = source_path.read_text(encoding="utf-8").rstrip("\n")
            pages = content.split("\n\f\n")

            self.assertEqual(len(pages), self.statistics.total_pages)
            for page_number, page in enumerate(pages, start=1):
                lines = page.splitlines()
                self.assertEqual(
                    lines[0],
                    f"{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}    第 {page_number} 页 / 共 {self.statistics.total_pages} 页",
                )
                if page_number < self.statistics.total_pages:
                    self.assertEqual(len(lines[1:]), LINES_PER_PAGE)
                else:
                    self.assertLessEqual(len(lines[1:]), LINES_PER_PAGE)

            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertIn(f"软件全称：{SOFTWARE_FULL_NAME}", manifest)
            self.assertIn(f"版本号：{SOFTWARE_VERSION}", manifest)


if __name__ == "__main__":
    unittest.main()
