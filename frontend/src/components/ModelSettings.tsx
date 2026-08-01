import { FormEvent, useCallback, useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Pencil, ShieldCheck, Trash2 } from "lucide-react";

import { api, getApiErrorInfo } from "../lib/api";
import { ModelConfig, ModelConfigStatus } from "../types";


const PROVIDER_DEFAULTS: Record<string, string> = {
  openai: "https://api.openai.com/v1",
  deepseek: "https://api.deepseek.com",
};

export interface ModelForm {
  provider: string;
  displayName: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  replaceApiKey: boolean;
  isEnabled: boolean;
}

const EMPTY_FORM: ModelForm = {
  provider: "openai",
  displayName: "",
  model: "",
  baseUrl: PROVIDER_DEFAULTS.openai,
  apiKey: "",
  replaceApiKey: false,
  isEnabled: true,
};

export function modelConfigErrorText(error: unknown): string {
  const info = getApiErrorInfo(error);
  const suffix = info.requestId ? `（请求 ID：${info.requestId}）` : "";
  return `${info.message}${suffix}`;
}

export function buildModelConfigPayload(form: ModelForm, editingId: string | null) {
  const common = {
    provider: form.provider,
    display_name: form.displayName,
    model: form.model,
    base_url: form.baseUrl,
  };
  if (!editingId) return { ...common, api_key: form.apiKey, is_default: false };
  return {
    ...common,
    api_key: form.replaceApiKey ? form.apiKey : null,
    replace_api_key: form.replaceApiKey,
    is_enabled: form.isEnabled,
  };
}

interface ModelSettingsProps {
  onStatusChange: (status: ModelConfigStatus) => void;
}

export function ModelSettings({ onStatusChange }: ModelSettingsProps) {
  const [status, setStatus] = useState<ModelConfigStatus | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ModelForm>(EMPTY_FORM);
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const response = await api.get<ModelConfigStatus & { success: true }>("/api/model-configs");
    setStatus(response.data);
    onStatusChange(response.data);
  }, [onStatusChange]);

  useEffect(() => {
    void refresh().catch((requestError) => setError(modelConfigErrorText(requestError)));
  }, [refresh]);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowKey(false);
  }

  function editConfig(config: ModelConfig) {
    setEditingId(config.id);
    setForm({
      provider: config.provider,
      displayName: config.display_name,
      model: config.model,
      baseUrl: config.base_url,
      apiKey: "",
      replaceApiKey: false,
      isEnabled: config.is_enabled,
    });
    setShowKey(false);
    setError("");
    setNotice("");
  }

  async function runAction(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (requestError) {
      setError(modelConfigErrorText(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    await runAction(async () => {
      if (editingId) {
        await api.put(`/api/model-configs/${editingId}`, buildModelConfigPayload(form, editingId));
      } else {
        await api.post("/api/model-configs", buildModelConfigPayload(form, null));
      }
      setForm((current) => ({ ...current, apiKey: "" }));
      resetForm();
      await refresh();
      setNotice("模型配置已安全保存。原始 API Key 不会再次显示。");
    });
  }

  async function handleTest() {
    await runAction(async () => {
      if (!form.apiKey) throw new Error("请先输入本次要测试的 API Key。");
      try {
        const response = await api.post<{ success: true; elapsed_ms: number }>("/api/model-configs/test", {
          provider: form.provider,
          model: form.model,
          base_url: form.baseUrl,
          api_key: form.apiKey,
        });
        setNotice(`连接成功，耗时 ${response.data.elapsed_ms} 毫秒。测试密钥已从输入框清空。`);
      } finally {
        setForm((current) => ({ ...current, apiKey: "" }));
      }
    });
  }

  async function verifySaved(config: ModelConfig) {
    await runAction(async () => {
      const response = await api.post<{ success: true; elapsed_ms: number }>(`/api/model-configs/${config.id}/verify`);
      await refresh();
      setNotice(`“${config.display_name}”连接成功，耗时 ${response.data.elapsed_ms} 毫秒。`);
    });
  }

  async function setDefault(config: ModelConfig) {
    await runAction(async () => {
      await api.post(`/api/model-configs/${config.id}/set-default`);
      await refresh();
      setNotice(`“${config.display_name}”已设为默认模型。`);
    });
  }

  async function removeConfig(config: ModelConfig) {
    if (!window.confirm(`确认删除“${config.display_name}”？删除后保存的密钥将立即失效。`)) return;
    await runAction(async () => {
      await api.delete(`/api/model-configs/${config.id}`);
      if (editingId === config.id) resetForm();
      await refresh();
      setNotice("模型配置已删除。");
    });
  }

  if (!status) return <section className="panel panel--loading">正在读取模型设置…</section>;
  if (!status.enabled) {
    return <section className="panel model-settings"><h3>模型设置尚未启用</h3><p>请联系管理员开启 BYOK 并配置独立加密主密钥。</p></section>;
  }

  return (
    <div className="model-settings">
      {(notice || error) && <div className={error ? "model-notice is-error" : "model-notice"}>{error || notice}</div>}
      <section className="panel">
        <div className="panel__header">
          <div><div className="eyebrow">安全凭据</div><h3>{editingId ? "编辑模型配置" : "添加模型配置"}</h3></div>
          <ShieldCheck size={24} />
        </div>
        <form className="model-form" onSubmit={(event) => void handleSave(event)} autoComplete="off">
          <div className="field-grid">
            <label className="field"><span>服务商</span><div className="field-control field-control--select"><select value={form.provider} onChange={(event) => { const provider = event.target.value; setForm((current) => ({ ...current, provider, baseUrl: PROVIDER_DEFAULTS[provider] ?? "" })); }}>{status.allowed_providers.map((provider) => <option key={provider} value={provider}>{provider}</option>)}</select></div></label>
            <label className="field"><span>配置名称</span><div className="field-control"><input required maxLength={64} value={form.displayName} onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))} /></div></label>
            <label className="field"><span>模型名称</span><div className="field-control"><input required maxLength={128} value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} /></div></label>
            <label className="field"><span>API Base URL</span><div className="field-control"><input required readOnly={form.provider !== "openai-compatible"} maxLength={512} value={form.baseUrl} onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))} /></div></label>
          </div>
          {editingId && !form.replaceApiKey ? (
            <button className="secondary-button" type="button" onClick={() => setForm((current) => ({ ...current, replaceApiKey: true }))}><KeyRound size={16} />替换密钥</button>
          ) : (
            <label className="field"><span>{editingId ? "新 API Key" : "API Key"}</span><div className="field-control model-key-field"><input required type={showKey ? "text" : "password"} autoComplete="new-password" spellCheck={false} value={form.apiKey} onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))} /><button type="button" className="ghost-button" onClick={() => setShowKey((value) => !value)}>{showKey ? "隐藏" : "显示"}</button></div></label>
          )}
          {editingId && <label className="model-checkbox"><input type="checkbox" checked={form.isEnabled} onChange={(event) => setForm((current) => ({ ...current, isEnabled: event.target.checked }))} />启用此配置</label>}
          <div className="inline-actions">
            <button className="secondary-button" type="button" disabled={busy || !form.apiKey} onClick={() => void handleTest()}>{busy ? "处理中…" : "测试连接"}</button>
            <button className="primary-button" type="submit" disabled={busy}>{busy ? "保存中…" : "保存配置"}</button>
            {editingId && <button className="ghost-button" type="button" disabled={busy} onClick={resetForm}>取消编辑</button>}
          </div>
        </form>
      </section>

      <section className="model-config-list" aria-label="已保存模型配置">
        {status.configs.length === 0 && <div className="panel model-empty">还没有保存模型配置。</div>}
        {status.configs.map((config) => (
          <article className="panel model-card" key={config.id}>
            <div className="model-card__heading"><div><h3>{config.display_name}</h3><p>{config.provider} · {config.model}</p></div>{config.is_default && <span className="status-chip"><CheckCircle2 size={15} />默认</span>}</div>
            <dl><div><dt>密钥</dt><dd>{config.masked_key}</dd></div><div><dt>API Base URL</dt><dd>{config.base_url}</dd></div><div><dt>状态</dt><dd>{config.is_enabled ? "已启用" : "已停用"}</dd></div><div><dt>上次验证</dt><dd>{config.last_verified_at ? `${config.last_verify_status === "success" ? "成功" : "失败"} · ${new Date(config.last_verified_at).toLocaleString("zh-CN")}` : "尚未验证"}</dd></div></dl>
            <div className="inline-actions"><button className="secondary-button" type="button" disabled={busy} onClick={() => editConfig(config)}><Pencil size={15} />编辑</button><button className="secondary-button" type="button" disabled={busy} onClick={() => void verifySaved(config)}>验证</button>{!config.is_default && <button className="secondary-button" type="button" disabled={busy || !config.is_enabled} onClick={() => void setDefault(config)}>设为默认</button>}<button className="ghost-button danger" type="button" disabled={busy} onClick={() => void removeConfig(config)}><Trash2 size={15} />删除</button></div>
          </article>
        ))}
      </section>
    </div>
  );
}
