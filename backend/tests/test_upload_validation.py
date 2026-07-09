import base64
import unittest

from fastapi import HTTPException

from backend.app.core.upload import ImageUploadPolicy, validate_image_payload


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF"


class UploadValidationTestCase(unittest.TestCase):
    def test_accepts_plain_base64_image_payload(self) -> None:
        encoded = base64.b64encode(PNG_BYTES).decode("ascii")
        result = validate_image_payload(encoded, ImageUploadPolicy(max_bytes=64))

        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.size_bytes, len(PNG_BYTES))
        self.assertEqual(result.base64_data, encoded)

    def test_accepts_data_url_and_normalizes_base64(self) -> None:
        encoded = base64.b64encode(JPEG_BYTES).decode("ascii")
        result = validate_image_payload(f"data:image/jpeg;base64,{encoded}", ImageUploadPolicy(max_bytes=64))

        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.base64_data, encoded)

    def test_rejects_unsupported_mime_type(self) -> None:
        encoded = base64.b64encode(b"hello").decode("ascii")
        with self.assertRaises(HTTPException) as rejected:
            validate_image_payload(f"data:text/plain;base64,{encoded}", ImageUploadPolicy(max_bytes=64))

        self.assertEqual(rejected.exception.status_code, 400)
        self.assertIn("仅支持", str(rejected.exception.detail))

    def test_rejects_payload_over_configured_size(self) -> None:
        encoded = base64.b64encode(PNG_BYTES * 10).decode("ascii")
        with self.assertRaises(HTTPException) as rejected:
            validate_image_payload(encoded, ImageUploadPolicy(max_bytes=16))

        self.assertEqual(rejected.exception.status_code, 413)
        self.assertIn("图片不能超过", str(rejected.exception.detail))

    def test_rejects_invalid_base64(self) -> None:
        with self.assertRaises(HTTPException) as rejected:
            validate_image_payload("not-valid-base64", ImageUploadPolicy(max_bytes=64))

        self.assertEqual(rejected.exception.status_code, 400)
        self.assertIn("Base64", str(rejected.exception.detail))


if __name__ == "__main__":
    unittest.main()
