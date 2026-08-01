import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAsyncGuard } from "../../hooks/useAsyncGuard";
import { api, getErrorMessage } from "../../lib/api";
import { MessageItem, SessionItem } from "../../types";
import {
  commitOptimisticMessages,
  createOptimisticMessagePair,
  failOptimisticMessages,
  removeOptimisticMessages,
  mergeOlderMessages,
  restoreDraftAfterFailure,
  shouldApplySessionResponse,
} from "./chatState";

const DEFAULT_SESSION_TITLE = "新会话";

interface ChatControllerOptions {
  selectedModel: string;
  selectedModelConfigId: string | null;
  onError: (message: string) => void;
}

function upsertSession(sessions: SessionItem[], nextSession: SessionItem): SessionItem[] {
  return [nextSession, ...sessions.filter((session) => session.id !== nextSession.id)];
}

export function useChatController({ selectedModel, selectedModelConfigId, onError }: ChatControllerOptions) {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [renameTitle, setRenameTitle] = useState(DEFAULT_SESSION_TITLE);
  const [draft, setDraft] = useState("");
  const [messageCursor, setMessageCursor] = useState<string | null>(null);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const sendAction = useAsyncGuard();
  const sessionAction = useAsyncGuard();
  const activeSessionIdRef = useRef<string | null>(null);
  const loadControllerRef = useRef<AbortController | null>(null);
  const retryRef = useRef<{ prompt: string; requestId: string } | null>(null);
  const sessionsVersionRef = useRef(0);
  const loadingCursorRef = useRef<string | null>(null);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => () => loadControllerRef.current?.abort(), []);

  const activeSession = useMemo(
    () => sessions.find((item) => item.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  );

  const syncSession = useCallback((nextSession: SessionItem) => {
    sessionsVersionRef.current += 1;
    setSessions((current) => upsertSession(current, nextSession));
  }, []);

  const clearActiveChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setRenameTitle(DEFAULT_SESSION_TITLE);
  }, []);

  const reset = useCallback(() => {
    setSessions([]);
    setDraft("");
    clearActiveChat();
  }, [clearActiveChat]);

  const refreshSessions = useCallback(async () => {
    const startedAtVersion = sessionsVersionRef.current;
    const response = await api.get<{ success: true; sessions: SessionItem[] }>("/api/chat/sessions", {
      params: { feature: "chat" },
    });
    if (sessionsVersionRef.current !== startedAtVersion) return;
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

  const loadSession = useCallback(
    async (sessionId: string) => {
      loadControllerRef.current?.abort();
      const controller = new AbortController();
      loadControllerRef.current = controller;
      activeSessionIdRef.current = sessionId;
      setActiveSessionId(sessionId);
      try {
          const response = await api.get<{ success: true; session: SessionItem; messages: MessageItem[]; message_pagination: { has_more: boolean; next_cursor: string | null } }>(
            `/api/chat/sessions/${sessionId}`,
            { signal: controller.signal, params: { message_limit: 100 } },
          );
          if (controller.signal.aborted || loadControllerRef.current !== controller) return;
          setMessages(response.data.messages);
          setRenameTitle(response.data.session.title);
          setHasOlderMessages(response.data.message_pagination.has_more);
          setMessageCursor(response.data.message_pagination.next_cursor);
          onError("");
        } catch (error) {
          if (controller.signal.aborted) return;
          onError(getErrorMessage(error));
        } finally {
          if (loadControllerRef.current === controller) loadControllerRef.current = null;
        }
    },
    [onError],
  );

  const ensureSession = useCallback(async () => {
    if (activeSessionId) {
      return activeSessionId;
    }
    const response = await api.post<{ success: true; session: SessionItem }>("/api/chat/sessions", {
      title: DEFAULT_SESSION_TITLE,
      feature: "chat",
      model_name: selectedModel,
      model_config_id: selectedModelConfigId,
    });
    setActiveSessionId(response.data.session.id);
    activeSessionIdRef.current = response.data.session.id;
    setRenameTitle(response.data.session.title);
    syncSession(response.data.session);
    return response.data.session.id;
  }, [activeSessionId, selectedModel, selectedModelConfigId, syncSession]);

  const sendMessage = useCallback(async () => {
    await sendAction.run(async () => {
      const prompt = draft.trim();
      if (!prompt) {
        return;
      }

      const retry = retryRef.current?.prompt === prompt ? retryRef.current : null;
      const requestId = retry?.requestId ?? crypto.randomUUID();
      retryRef.current = null;
      const optimistic = createOptimisticMessagePair(prompt, requestId);
      setMessages((current) => [...removeOptimisticMessages(current, requestId), ...optimistic.messages]);
      setDraft("");
      onError("");
      let targetSessionId: string | null = activeSessionId;

      try {
        const sessionId = await ensureSession();
        targetSessionId = sessionId;
        const response = await api.post<{
          success: true;
          user_message: MessageItem;
          assistant_message: MessageItem;
          session: SessionItem;
        }>(
          `/api/chat/sessions/${sessionId}/messages`,
          { message: prompt, model_name: selectedModel, model_config_id: selectedModelConfigId },
          { headers: { "X-Idempotency-Key": requestId } },
        );

        if (shouldApplySessionResponse(activeSessionIdRef.current, sessionId)) {
          setMessages((current) =>
            commitOptimisticMessages(current, requestId, [response.data.user_message, response.data.assistant_message]),
          );
          setRenameTitle(response.data.session.title);
        }
        syncSession(response.data.session);
      } catch (error) {
        if (!targetSessionId || activeSessionIdRef.current === targetSessionId) {
          setMessages((current) => failOptimisticMessages(current, requestId));
          setDraft((current) => restoreDraftAfterFailure(current, prompt));
        }
        retryRef.current = { prompt, requestId };
        onError(getErrorMessage(error));
      }
    });
  }, [draft, ensureSession, onError, selectedModel, selectedModelConfigId, sendAction, syncSession]);

  const renameActiveSession = useCallback(async () => {
    if (!activeSessionId) {
      return;
    }
    await sessionAction.run(async () => {
      try {
        const response = await api.patch<{ success: true; session: SessionItem }>(
          `/api/chat/sessions/${activeSessionId}`,
          { title: renameTitle },
        );
        syncSession(response.data.session);
        setRenameTitle(response.data.session.title);
        onError("");
      } catch (error) {
        onError(getErrorMessage(error));
      }
    });
  }, [activeSessionId, onError, renameTitle, sessionAction, syncSession]);

  const deleteActiveSession = useCallback(async () => {
    if (!activeSessionId || sendAction.isRunning()) {
      return false;
    }
    const deleted = await sessionAction.run(async () => {
      try {
        await api.delete(`/api/chat/sessions/${activeSessionId}`);
        setSessions((current) => current.filter((session) => session.id !== activeSessionId));
        clearActiveChat();
        onError("");
        return true;
      } catch (error) {
        onError(getErrorMessage(error));
        return false;
      }
    });
    return deleted ?? false;
  }, [activeSessionId, clearActiveChat, onError, sendAction, sessionAction]);

  const updateDraft = useCallback((value: string) => {
    if (retryRef.current && value.trim() !== retryRef.current.prompt) retryRef.current = null;
    setDraft(value);
  }, []);

  const loadOlderMessages = useCallback(async () => {
    const sessionId = activeSessionIdRef.current;
    if (!sessionId || !messageCursor || loadingCursorRef.current === messageCursor) return;
    loadingCursorRef.current = messageCursor;
    try {
      const response = await api.get<{ success: true; messages: MessageItem[]; message_pagination: { has_more: boolean; next_cursor: string | null } }>(
        `/api/chat/sessions/${sessionId}`,
        { params: { message_limit: 100, message_cursor: messageCursor } },
      );
      if (activeSessionIdRef.current !== sessionId) return;
      setMessages((current) => mergeOlderMessages(current, response.data.messages));
      setHasOlderMessages(response.data.message_pagination.has_more);
      setMessageCursor(response.data.message_pagination.next_cursor);
    } catch (error) {
      onError(getErrorMessage(error));
    } finally {
      loadingCursorRef.current = null;
    }
  }, [messageCursor, onError]);

  return {
    sessions,
    activeSessionId,
    activeSession,
    messages,
    renameTitle,
    draft,
    sendBusy: sendAction.busy,
    sessionBusy: sessionAction.busy,
    hasOlderMessages,
    setRenameTitle,
    setDraft: updateDraft,
    refreshSessions,
    loadSession,
    loadOlderMessages,
    sendMessage,
    renameActiveSession,
    deleteActiveSession,
    clearActiveChat,
    reset,
  };
}
