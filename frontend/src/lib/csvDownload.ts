import axios from "axios";

import { api } from "./api";

export async function downloadCsv(endpoint: string, params: Record<string, string>, fallbackName: string) {
  try {
    const response = await api.get<Blob>(endpoint, {
      params: Object.fromEntries(Object.entries(params).filter(([, value]) => value)), responseType: "blob",
    });
    if (!String(response.headers["content-type"] ?? "").toLowerCase().startsWith("text/csv")) {
      throw new Error("导出响应格式异常，未下载文件。请稍后重试。");
    }
    const disposition = String(response.headers["content-disposition"] ?? "");
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    let filename = fallbackName;
    if (encoded) {
      try { filename = decodeURIComponent(encoded); } catch { /* 采用本地默认文件名。 */ }
    }
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    try { anchor.click(); } finally {
      anchor.remove();
      // 下载开始后释放临时 URL；不把文件放入浏览器持久存储。
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    const count = Number(response.headers["x-export-row-count"]);
    return { filename, count: Number.isInteger(count) && count >= 0 ? count : undefined };
  } catch (requestError) {
    if (axios.isAxiosError(requestError) && requestError.response?.data instanceof Blob) {
      try { requestError.response.data = JSON.parse(await requestError.response.data.text()); } catch { /* 非 JSON 时用统一错误提示。 */ }
    }
    throw requestError;
  }
}
