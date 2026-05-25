import { ClipboardCopy, SendHorizonal, Sparkles } from "lucide-react";

import { MessageItem, SessionItem } from "../types";

interface ChatWorkspaceProps {
  messages: MessageItem[];
  draft: string;
  selectedModel: string;
  maxMessageLength: number;
  activeSession: SessionItem | null;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onUsePrompt: (prompt: string) => void;
  onOpenFeature: (feature: "vision" | "decision") => void;
}

const prompts = [
  "帮我整理一份本周巡田重点",
  "把这段农技建议改成更容易听懂的话",
  "帮我解释一段代码",
  "生成一个学习计划",
];

export function ChatWorkspace(props: ChatWorkspaceProps) {
  const {
    messages,
    draft,
    selectedModel,
    maxMessageLength,
    activeSession,
    onDraftChange,
    onSend,
    onUsePrompt,
    onOpenFeature,
  } = props;

  return (
    <section className="workspace-grid">
      <div className="panel panel--chat">
        <div className="panel__header">
          <div>
            <h3>对话区</h3>
            <p>{activeSession ? "当前会话会持续保存在后端。" : "发出第一条消息后，会自动创建会话记录。"}</p>
          </div>
          <div className="panel__meta">模型：{selectedModel}</div>
        </div>

        <div className="chat-thread">
          {messages.length === 0 ? (
            <div className="empty-surface">
              <Sparkles size={20} />
              <p>先试一个示例问题，或者直接输入你自己的内容。</p>
              <div className="prompt-grid">
                {prompts.map((prompt) => (
                  <button key={prompt} className="prompt-chip" type="button" onClick={() => onUsePrompt(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <article
                key={message.id}
                className={message.role === "user" ? "message-row message-row--user" : "message-row"}
              >
                <div className="message-bubble">
                  <div className="message-bubble__role">{message.role === "user" ? "你" : "云寻 AI"}</div>
                  <div className="message-bubble__content">{message.content}</div>
                  {message.role === "assistant" && (
                    <button
                      className="ghost-button message-copy"
                      type="button"
                      onClick={() => navigator.clipboard.writeText(message.content)}
                    >
                      <ClipboardCopy size={15} />
                      复制
                    </button>
                  )}
                </div>
              </article>
            ))
          )}
        </div>

        <div className="composer">
          <textarea
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder="输入你的问题。Enter 发送，Shift + Enter 换行。"
            maxLength={maxMessageLength}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (draft.trim()) {
                  onSend();
                }
              }
            }}
          />
          <div className="composer__footer">
            <span>单次输入上限 {maxMessageLength} 字</span>
            <button className="primary-button" type="button" onClick={onSend} disabled={!draft.trim()}>
              <SendHorizonal size={16} />
              发送
            </button>
          </div>
        </div>
      </div>

      <aside className="panel panel--side">
        <div className="panel__header">
          <div>
            <h3>当前上下文</h3>
            <p>把会话状态、常用问题和执行提醒集中在一边，便于持续操作。</p>
          </div>
        </div>
        <div className="stat-list">
          <div className="stat-card">
            <span>会话标题</span>
            <strong>{activeSession?.title || "尚未创建"}</strong>
          </div>
          <div className="stat-card">
            <span>消息条数</span>
            <strong>{messages.length}</strong>
          </div>
          <div className="stat-card">
            <span>推荐做法</span>
            <strong>先给结论，再说原因，最后给今天能做的操作</strong>
          </div>
          <div className="stat-card">
            <span>田间诊断</span>
            <strong>上传作物照片，结合现场描述做初步判断。</strong>
            <button className="secondary-button" type="button" onClick={() => onOpenFeature("vision")}>
              去诊断台
            </button>
          </div>
          <div className="stat-card">
            <span>今日农活</span>
            <strong>把降雨、墒情和气温合成当日可执行建议。</strong>
            <button className="secondary-button" type="button" onClick={() => onOpenFeature("decision")}>
              去计划台
            </button>
          </div>
        </div>
      </aside>
    </section>
  );
}
