import { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { api, getErrorMessage, setAuthToken } from "./lib/api";
import { FeatureKey, HealthPayload, MessageItem, SessionItem, User } from "./types";

const TOKEN_STORAGE_KEY = "yunxun.auth.token";
const DEFAULT_SESSION_TITLE = "新会话";
const VisionWorkspace = lazy(() =>
  import("./components/VisionWorkspace").then((module) => ({ default: module.VisionWorkspace })),
);
const DecisionWorkspace = lazy(() =>
  import("./components/DecisionWorkspace").then((module) => ({ default: module.DecisionWorkspace })),
);

function readStoredToken(): string {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
}

function persistToken(token: string): void {
  if (!token) {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    return;
  }

  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

function upsertSession(sessions: SessionItem[], nextSession: SessionItem): SessionItem[] {
  return [nextSession, ...sessions.filter((session) => session.id !== nextSession.id)];
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = () => reject(new Error("图片读取失败。"));
    reader.readAsDataURL(file);
  });
}

export default function App() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [authLoading, setAuthLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState(readStoredToken());
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({ username: "", password: "", displayName: "" });
  const [user, setUser] = useState<User | null>(null);
  const [activeFeature, setActiveFeature] = useState<FeatureKey>("chat");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [renameTitle, setRenameTitle] = useState(DEFAULT_SESSION_TITLE);
  const [settingsName, setSettingsName] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [chatDraft, setChatDraft] = useState("");
  const [visionFile, setVisionFile] = useState<File | null>(null);
  const [visionPreview, setVisionPreview] = useState<string | null>(null);
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

  const models = useMemo(() => health?.available_models ?? [], [health]);
  const activeSession = useMemo(
    () => sessions.find((item) => item.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  );

  const syncSession = useCallback((nextSession: SessionItem) => {
    setSessions((current) => upsertSession(current, nextSession));
  }, []);

  const clearActiveChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setRenameTitle(DEFAULT_SESSION_TITLE);
  }, []);

  const loadMe = useCallback(async (availableModels: string[] = models) => {
    const response = await api.get<{ success: true; user: User }>("/api/me");
    setUser(response.data.user);
    setSettingsName(response.data.user.display_name);
    setSelectedModel((current) => current || response.data.user.preferred_model || availableModels[0] || "");
  }, [models]);

  const refreshSessions = useCallback(async () => {
    const response = await api.get<{ success: true; sessions: SessionItem[] }>("/api/chat/sessions", {
      params: { feature: "chat" },
    });

    setSessions(response.data.sessions);
    setActiveSessionId((current) => {
      if (current && !response.data.sessions.some((item) => item.id === current)) {
        setMessages([]);
        setRenameTitle(DEFAULT_SESSION_TITLE);
        return null;
      }

      return current;
    });
  }, []);

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

  useEffect(() => {
    setAuthToken(token || null);
    persistToken(token);
  }, [token]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await api.get<HealthPayload>("/api/health");
        setHealth(response.data);

        if (token) {
          await Promise.all([loadMe(response.data.available_models), refreshSessions()]);
        }
      } catch (requestError) {
        setError(getErrorMessage(requestError, "后端未连接，请先启动服务。"));
      } finally {
        setBootLoading(false);
      }
    }

    void bootstrap();
  }, [loadMe, refreshSessions, token]);

  useEffect(() => {
    if (!visionFile) {
      setVisionPreview(null);
      return;
    }

    const preview = URL.createObjectURL(visionFile);
    setVisionPreview(preview);

    return () => URL.revokeObjectURL(preview);
  }, [visionFile]);

  const loadSession = useCallback(async (sessionId: string) => {
    setBusy(true);
    try {
      const response = await api.get<{ success: true; session: SessionItem; messages: MessageItem[] }>(
        `/api/chat/sessions/${sessionId}`,
      );
      setActiveSessionId(sessionId);
      setMessages(response.data.messages);
      setRenameTitle(response.data.session.title);
      setActiveFeature("chat");
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }, []);

  const ensureSession = useCallback(async () => {
    if (activeSessionId) {
      return activeSessionId;
    }

    const response = await api.post<{ success: true; session: SessionItem }>("/api/chat/sessions", {
      title: DEFAULT_SESSION_TITLE,
      feature: "chat",
      model_name: selectedModel,
    });

    setActiveSessionId(response.data.session.id);
    setRenameTitle(response.data.session.title);
    syncSession(response.data.session);
    return response.data.session.id;
  }, [activeSessionId, selectedModel, syncSession]);

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthLoading(true);
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
      void refreshSessions();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleGuestLogin() {
    setAuthLoading(true);
    setError("");

    try {
      const response = await api.post<{ success: true; token: string; user: User }>("/api/auth/guest");
      applyAuthenticatedUser(response.data.token, response.data.user);
      void refreshSessions();
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleSaveSettings() {
    if (!settingsName.trim()) {
      setError("显示名称不能为空。");
      return;
    }

    setBusy(true);
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
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // no-op
    }

    setAuthToken(null);
    setToken("");
    setUser(null);
    setSessions([]);
    clearActiveChat();
  }

  async function handleRenameSession() {
    if (!activeSessionId) {
      return;
    }

    setBusy(true);
    try {
      const response = await api.patch<{ success: true; session: SessionItem }>(`/api/chat/sessions/${activeSessionId}`, {
        title: renameTitle,
      });
      syncSession(response.data.session);
      setRenameTitle(response.data.session.title);
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSession() {
    if (!activeSessionId) {
      return;
    }

    setBusy(true);
    try {
      await api.delete(`/api/chat/sessions/${activeSessionId}`);
      setSessions((current) => current.filter((session) => session.id !== activeSessionId));
      clearActiveChat();
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleSendChat() {
    const prompt = chatDraft.trim();
    if (!prompt) {
      return;
    }

    setBusy(true);
    try {
      const sessionId = await ensureSession();
      const response = await api.post<{
        success: true;
        user_message: MessageItem;
        assistant_message: MessageItem;
        session: SessionItem;
      }>(`/api/chat/sessions/${sessionId}/messages`, {
        message: prompt,
        model_name: selectedModel,
      });

      setMessages((current) => [...current, response.data.user_message, response.data.assistant_message]);
      setRenameTitle(response.data.session.title);
      setChatDraft("");
      syncSession(response.data.session);
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleVisionSubmit() {
    if (!visionFile) {
      setError("请先选择一张图片。");
      return;
    }

    setBusy(true);
    try {
      const response = await api.post<{ success: true; reply: string }>("/api/vision", {
        image_base64: await fileToBase64(visionFile),
        crop: visionCrop,
        symptom: visionSymptom,
      });
      setVisionResult(response.data.reply);
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleDecisionSubmit() {
    setBusy(true);
    try {
      const response = await api.post<{ success: true; reply: string }>("/api/decision", {
        crop: decisionForm.crop,
        stage: decisionForm.stage,
        rain_prob: decisionForm.rainProb,
        soil_moisture: decisionForm.soilMoisture,
        temperature: decisionForm.temperature,
      });
      setDecisionResult(response.data.reply);
      setError("");
    } catch (requestError) {
      setError(getErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  const handleAuthFormChange = useCallback((field: "username" | "password" | "displayName", value: string) => {
    setAuthForm((current) => ({ ...current, [field]: value }));
  }, []);

  const handleGuestLoginAction = useCallback(() => {
    void handleGuestLogin();
  }, []);

  const handleCreateSession = useCallback(() => {
    setActiveFeature("chat");
    clearActiveChat();
  }, [clearActiveChat]);

  const handleSelectSession = useCallback((sessionId: string) => {
    void loadSession(sessionId);
  }, [loadSession]);

  const handleRenameSessionAction = useCallback(() => {
    void handleRenameSession();
  }, [activeSessionId, renameTitle]);

  const handleDeleteSessionAction = useCallback(() => {
    void handleDeleteSession();
  }, [activeSessionId]);

  const handleSaveSettingsAction = useCallback(() => {
    void handleSaveSettings();
  }, [selectedModel, settingsName]);

  const handleLogoutAction = useCallback(() => {
    void handleLogout();
  }, []);

  const handleSendChatAction = useCallback(() => {
    void handleSendChat();
  }, [activeSessionId, chatDraft, ensureSession, messages, selectedModel]);

  const handleVisionSubmitAction = useCallback(() => {
    void handleVisionSubmit();
  }, [visionCrop, visionFile, visionSymptom]);

  const handleDecisionSubmitAction = useCallback(() => {
    void handleDecisionSubmit();
  }, [decisionForm]);

  if (bootLoading) {
    return <div className="app-loading">正在加载云寻 AI...</div>;
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
          loading={authLoading}
          form={authForm}
          onModeChange={setAuthMode}
          onChange={handleAuthFormChange}
          onSubmit={handleAuthSubmit}
          onGuestLogin={handleGuestLoginAction}
        />
      </div>
    );
  }

  return (
    <div className="app-shell">
      {error && <div className="toast-banner">{error}</div>}
      <Sidebar
        user={user}
        activeFeature={activeFeature}
        sessions={sessions}
        activeSessionId={activeSessionId}
        renameTitle={renameTitle}
        settingsName={settingsName}
        selectedModel={selectedModel || models[0] || ""}
        models={models}
        onFeatureChange={setActiveFeature}
        onCreateSession={handleCreateSession}
        onSelectSession={handleSelectSession}
        onRenameTitleChange={setRenameTitle}
        onRenameSession={handleRenameSessionAction}
        onDeleteSession={handleDeleteSessionAction}
        onSettingsNameChange={setSettingsName}
        onModelChange={setSelectedModel}
        onSaveSettings={handleSaveSettingsAction}
        onLogout={handleLogoutAction}
      />

      <main className="workspace">
        <TopBar health={health} activeFeature={activeFeature} />

        {busy && <div className="inline-status">正在处理中，请稍候...</div>}

        {activeFeature === "chat" && (
          <ChatWorkspace
            messages={messages}
            draft={chatDraft}
            selectedModel={selectedModel || models[0] || "未配置"}
            maxMessageLength={health.max_message_length}
            activeSession={activeSession}
            onDraftChange={setChatDraft}
            onSend={handleSendChatAction}
            onUsePrompt={setChatDraft}
            onOpenFeature={setActiveFeature}
          />
        )}

        {activeFeature === "vision" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载田间诊断模块...</div>}>
            <VisionWorkspace
              previewUrl={visionPreview}
              crop={visionCrop}
              symptom={visionSymptom}
              result={visionResult}
              modelMode={health.mode}
              aiConfigured={health.ai_configured}
              onFileChange={setVisionFile}
              onCropChange={setVisionCrop}
              onSymptomChange={setVisionSymptom}
              onSubmit={handleVisionSubmitAction}
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
              onChange={(field, value) => setDecisionForm((current) => ({ ...current, [field]: value }))}
              onSubmit={handleDecisionSubmitAction}
            />
          </Suspense>
        )}
      </main>
    </div>
  );
}
