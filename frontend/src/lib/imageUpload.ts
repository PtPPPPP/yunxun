export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

export type AllowedImageType = (typeof ALLOWED_IMAGE_TYPES)[number];

export interface ImageValidationResult {
  ok: boolean;
  message: string;
}

export function imageAcceptValue(): string {
  return ALLOWED_IMAGE_TYPES.join(",");
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function validateImageFile(file: File | null, maxBytes = MAX_IMAGE_BYTES): ImageValidationResult {
  if (!file) {
    return { ok: false, message: "请先选择一张图片。" };
  }
  if (!ALLOWED_IMAGE_TYPES.includes(file.type as AllowedImageType)) {
    return { ok: false, message: "仅支持 JPG、PNG 或 WebP 图片。" };
  }
  if (file.size <= 0) {
    return { ok: false, message: "图片文件为空，请重新选择。" };
  }
  if (file.size > maxBytes) {
    return { ok: false, message: `图片不能超过 ${formatFileSize(maxBytes)}。` };
  }
  return { ok: true, message: "" };
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      const [, base64 = ""] = result.split(",", 2);
      if (!base64) {
        reject(new Error("图片转换失败，请重新选择。"));
        return;
      }
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("图片读取失败。"));
    reader.readAsDataURL(file);
  });
}
