import { useState } from "react";

import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { downloadCsv } from "../lib/csvDownload";
import { getErrorMessage } from "../lib/api";

interface CsvExportButtonProps {
  endpoint: string;
  params: object;
  label: string;
  unit: string;
  disabled?: boolean;
}

export function CsvExportButton({ endpoint, params, label, unit, disabled }: CsvExportButtonProps) {
  const action = useAsyncGuard();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function download() {
    await action.run(async () => {
      setMessage(""); setError("");
      try {
        const result = await downloadCsv(endpoint, { ...params } as Record<string, string>, `${label}.csv`);
        setMessage(result.count === 0 ? "没有符合条件的数据，已生成仅含表头的 CSV 并开始下载。" : `已生成点击时筛选范围${result.count === undefined ? "" : `的 ${result.count} ${unit}`}并开始下载：${result.filename}`);
      } catch (requestError) { setError(getErrorMessage(requestError, "CSV 导出失败，请稍后重试。")); }
    });
  }
  return <div className="csv-export">
    <button type="button" className="secondary-button" disabled={disabled || action.busy} onClick={() => void download()}>{action.busy ? "导出中…" : label}</button>
    {message && <p className="csv-export-feedback" role="status">{message}</p>}
    {error && <p className="csv-export-feedback" role="alert">{error}</p>}
  </div>;
}
