import { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { useChatController } from "./features/chat/useChatController";
import { useAsyncGuard } from "./hooks/useAsyncGuard";
import { api, getErrorMessage, setAuthToken } from "./lib/api";
import { fileToBase64, formatFileSize, imageAcceptValue, validateImageFile } from "./lib/imageUpload";
import { clearStoredAuthToken, persistAuthToken, readStoredAuthToken } from "./lib/tokenStorage";
import { FeatureKey, HealthPayload, User } from "./types";

const VisionWorkspace = lazy(() =>
  import("./components/VisionWorkspace").then((module) => ({ default: module.VisionWorkspace })),
);
const DecisionWorkspace = lazy(() =>
  import("./components/DecisionWorkspace").then((module) => ({ default: module.DecisionWorkspace })),
);

export default function App() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [error, setError] = useState("");
  const [token, setToken] = useState(readStoredAuthToken());
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({ username: "", password: "", displayName: "" });
  const [user, setUser] = useState<User | null>(null);
  const [activeFeature, setActiveFeature] = useState<FeatureKey>("chat");
  const [settingsName, setSettingsName] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const [visionFile, setVisionFile] = useState<File | null>(null);
  const [visionPreview, setVisionPreview] = useState<string | null>(null);
  const [visionUploadError, setVisionUploadError] = useState("");
  const [visionCrop, setVisionCrop] = useState("玉米");
  const [visionSymptom, setVisionSymptom] = useState("");
  const [visionResult, setVisionResult] = useState("");
  const [decisionForm, setDecisionForm] = useState({
    crop: "玉米",
    stage: "快速生长期",
    rainProb: 55,
    soilMoisture: 42,
    temperature: 24.5,
  });
  const [decisionResult, setDecisionResult] = useState("");

  const authAction = useAsyncGuard();
  const settingsAction = useAsyncGuard();
  const visionAction = useAsyncGuard();
  const decisionAction = useAsyncGuard();
  const models = useMemo(() => health?.available_models ?? [], [health]);
  const handleError = useCallback((message: string) => setError(message), []);
  const chat = useChatController({ selectedModel, onError: handleError });

  const loadMe = useCallback(async (availableModels: string[]) => {
    const response = await api.get<{ success: true; user: User }>("/api/me");
    setUser(response.data.user);
    setSettingsName(response.data.user.display_name);
    setSelectedModel((current) => current || response.data.user.preferred_model || availableModels[0] || "");
  }, []);

  useEffect(() => {
    setAuthToken(token || null);
    try {
      persistAuthToken(token);
    } catch (storageError) {
      setError(getErrorMessage(storageError));
    }
  }, [token]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await api.get<HealthPayload>("/api/health");
        setHealth(response.data);
        if (token) {
          await Promise.all([loadMe(response.data.available_models), chat.refreshSessions()]);
        }
      } catch (requestError) {
        setError(getErrorMessage(requestError, "后端未连接，请先启动服务。"));
      } finally {
        setBootLoading(false);
      }
    }

    void bootstrap();
  }, [chat.refreshSessions, loadMe, token]);

  useEffect(() => {
    if (!visionFile) {
      setVisionPreview(null);
      return;
    }
    const preview = URL.createObjectURL(visionFile);
    setVisionPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [visionFile]);

  const applyAuthenticatedUser = useCallback(
    (nextToken: string, nextUser: User) => {
      setAuthToken(nextToken);
      setToken(nextToken);
      setUser(nextUser);
      setSettingsName(nextUser.display_name);
      setSelectedModel(nextUser.preferred_model || models[0] || "");
      setAuthForm({ username: "", password: "", displayName: "" });
    },
    [models],
  );

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await authAction.run(async () => {
      setError("");
      try {
        const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
        const payload =
          authMode === "login"
            ? { username: authForm.username, password: authForm.password }
            : {
                username: authForm.username,
                password: authForm.password,
                display_name: authForm.displayName,
              };
        const response = await api.post<{ success: true; token: string; user: User }>(endpoint, payload);
        applyAuthenticatedUser(response.data.token, response.data.user);
        await chat.refreshSessions();
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleGuestLogin() {
    await authAction.run(async () => {
      setError("");
      try {
        const response = await api.post<{ success: true; token: string; user: User }>("/api/auth/guest");
        applyAuthenticatedUser(response.data.token, response.data.user);
        await chat.refreshSessions();
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleSaveSettings() {
    await settingsAction.run(async () => {
      if (!settingsName.trim()) {
        setError("显示名称不能为空。");
        return;
      }
      try {
        const response = await api.patch<{ success: true; user: User }>("/api/me/profile", {
          display_name: settingsName,
          preferred_model: selectedModel,
        });
        setUser(response.data.user);
        setSettingsName(response.data.user.display_name);
        setError("");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // 本地状态仍需清理，避免失效后端阻止用户退出。
    }
    setAuthToken(null);
    clearStoredAuthToken();
    setToken("");
    setUser(null);
    chat.reset();
  }

  const handleVisionFileChange = useCallback(
    (file: File | null) => {
      if (!file) {
        setVisionFile(null);
        setVisionUploadError("");
        return;
      }
      const validation = validateImageFile(file, health?.upload_max_bytes);
      if (!validation.ok) {
        setVisionFile(null);
        setVisionUploadError(validation.message);
        setError(validation.message);
        return;
      }
      setVisionFile(file);
      setVisionUploadError("");
      setError("");
    },
    [health?.upload_max_bytes],
  );

  const handleClearVisionFile = useCallback(() => {
    setVisionFile(null);
    setVisionPreview(null);
    setVisionUploadError("");
  }, []);

  async function handleVisionSubmit() {
    await visionAction.run(async () => {
      if (!visionFile) {
        setError("请先选择一张图片。");
        return;
      }
      const validation = validateImageFile(visionFile, health?.upload_max_bytes);
      if (!validation.ok) {
        setVisionUploadError(validation.message);
        setError(validation.message);
        return;
      }
      try {
        const requestId = crypto.randomUUID();
        const response = await api.post<{ success: true; reply: string }>(
          "/api/vision",
          {
            image_base64: await fileToBase64(visionFile),
            crop: visionCrop,
            symptom: visionSymptom,
          },
          { headers: { "X-Idempotency-Key": requestId } },
        );
        setVisionResult(response.data.reply);
        setError("");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleDecisionSubmit() {
    await decisionAction.run(async () => {
      try {
        const requestId = crypto.randomUUID();
        const response = await api.post<{ success: true; reply: string }>(
          "/api/decision",
          {
            crop: decisionForm.crop,
            stage: decisionForm.stage,
            rain_prob: decisionForm.rainProb,
            soil_moisture: decisionForm.soilMoisture,
            temperature: decisionForm.temperature,
          },
          { headers: { "X-Idempotency-Key": requestId } },
        );
        setDecisionResult(response.data.reply);
        setError("");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function confirmDeleteSession() {
    const deleted = await chat.deleteActiveSession();
    if (deleted) {
      setDeleteDialogOpen(false);
    }
  }

  if (bootLoading) {
    return <div className="app-loading">正在加载云寻AI...</div>;
  }
  if (!health) {
    return <div className="app-loading">{error || "后端未连接，请先启动服务。"}</div>;
  }
  if (!user) {
    return (
      <div className="app-shell app-shell--auth">
        {error && <div className="toast-banner">{error}</div>}
        <AuthScreen
          mode={authMode}
          backendMode={health.mode}
          backendUrl={health.backend_url || api.defaults.baseURL || ""}
          modelStatus={health.model_status}
          environment={health.environment}
          warnings={health.warnings}
          loading={authAction.busy}
          form={authForm}
          onModeChange={setAuthMode}
          onChange={(field, value) => setAuthForm((current) => ({ ...current, [field]: value }))}
          onSubmit={handleAuthSubmit}
          onGuestLogin={() => void handleGuestLogin()}
        />
      </div>
    );
  }

  const anyBusy = chat.sendBusy || chat.sessionBusy || settingsAction.busy || visionAction.busy || decisionAction.busy;

  return (
    <div className="app-shell">
      {error && <div className="toast-banner">{error}</div>}
      <button
        className={sidebarOpen ? "sidebar-backdrop is-visible" : "sidebar-backdrop"}
        type="button"
        aria-label="关闭导航"
        onClick={() => setSidebarOpen(false)}
      />
      <Sidebar
        user={user}
        activeFeature={activeFeature}
        sessions={chat.sessions}
        activeSessionId={chat.activeSessionId}
        renameTitle={chat.renameTitle}
        settingsName={settingsName}
        selectedModel={selectedModel || models[0] || ""}
        models={models}
        mobileOpen={sidebarOpen}
        sessionBusy={chat.sessionBusy}
        settingsBusy={settingsAction.busy}
        onClose={() => setSidebarOpen(false)}
        onFeatureChange={setActiveFeature}
        onCreateSession={() => {
          setActiveFeature("chat");
          chat.clearActiveChat();
        }}
        onSelectSession={(sessionId) => {
          setActiveFeature("chat");
          void chat.loadSession(sessionId);
        }}
        onRenameTitleChange={chat.setRenameTitle}
        onRenameSession={() => void chat.renameActiveSession()}
        onDeleteSession={() => setDeleteDialogOpen(true)}
        onSettingsNameChange={setSettingsName}
        onModelChange={setSelectedModel}
        onSaveSettings={() => void handleSaveSettings()}
        onLogout={() => void handleLogout()}
      />

      <main className="workspace">
        <TopBar health={health} activeFeature={activeFeature} onOpenNavigation={() => setSidebarOpen(true)} />
        {anyBusy && <div className="inline-status">正在处理当前操作，请稍候...</div>}

        {activeFeature === "chat" && (
          <ChatWorkspace
            messages={chat.messages}
            draft={chat.draft}
            selectedModel={selectedModel || models[0] || "未配置"}
            maxMessageLength={health.max_message_length}
            activeSession={chat.activeSession}
            busy={chat.sendBusy}
            hasOlderMessages={chat.hasOlderMessages}
            onLoadOlder={chat.loadOlderMessages}
            onDraftChange={chat.setDraft}
            onSend={() => void chat.sendMessage()}
            onUsePrompt={chat.setDraft}
            onOpenFeature={setActiveFeature}
          />
        )}

        {activeFeature === "vision" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载田间诊断模块...</div>}>
            <VisionWorkspace
              previewUrl={visionPreview}
              fileName={visionFile?.name ?? ""}
              fileSizeText={visionFile ? formatFileSize(visionFile.size) : ""}
              maxSizeText={formatFileSize(health.upload_max_bytes)}
              uploadError={visionUploadError}
              accept={imageAcceptValue()}
              crop={visionCrop}
              symptom={visionSymptom}
              result={visionResult}
              modelMode={health.mode}
              aiConfigured={health.ai_configured}
              busy={visionAction.busy}
              onFileChange={handleVisionFileChange}
              onClearFile={handleClearVisionFile}
              onCropChange={setVisionCrop}
              onSymptomChange={setVisionSymptom}
              onSubmit={() => void handleVisionSubmit()}
            />
          </Suspense>
        )}

        {activeFeature === "decision" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载今日农活模块...</div>}>
            <DecisionWorkspace
              crop={decisionForm.crop}
              stage={decisionForm.stage}
              rainProb={decisionForm.rainProb}
              soilMoisture={decisionForm.soilMoisture}
              temperature={decisionForm.temperature}
              result={decisionResult}
              busy={decisionAction.busy}
              onChange={(field, value) => setDecisionForm((current) => ({ ...current, [field]: value }))}
              onSubmit={() => void handleDecisionSubmit()}
            />
          </Suspense>
        )}
      </main>

      <ConfirmDialog
        open={deleteDialogOpen}
        title="删除当前会话？"
        description="会话和其中的消息会永久删除，删除后无法恢复。"
        confirmLabel="确认删除"
        busy={chat.sessionBusy || chat.sendBusy}
        onConfirm={() => void confirmDeleteSession()}
        onCancel={() => setDeleteDialogOpen(false)}
      />
    </div>
  );
}
