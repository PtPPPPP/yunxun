import { describe, expect, it } from "vitest";

import { buildModelConfigPayload, ModelForm } from "./ModelSettings";


const form: ModelForm = {
  provider: "openai",
  displayName: "我的 OpenAI",
  model: "gpt-test",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "sk-temporary-test-key",
  replaceApiKey: false,
  isEnabled: true,
};

describe("模型配置请求", () => {
  it("新建配置只通过请求体提交密钥，不生成 URL 参数", () => {
    const payload = buildModelConfigPayload(form, null);
    expect(payload).toMatchObject({ api_key: "sk-temporary-test-key", is_default: false });
    expect(JSON.stringify(payload)).not.toContain("encrypted_api_key");
  });

  it("编辑时默认不回填或替换旧密钥", () => {
    const payload = buildModelConfigPayload({ ...form, apiKey: "" }, "config-1");
    expect(payload).toMatchObject({ api_key: null, replace_api_key: false });
  });

  it("只有显式替换时才提交新密钥", () => {
    const payload = buildModelConfigPayload({ ...form, replaceApiKey: true }, "config-1");
    expect(payload).toMatchObject({ api_key: "sk-temporary-test-key", replace_api_key: true });
  });
});
