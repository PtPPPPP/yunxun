export type FeatureKey = "chat" | "vision" | "decision" | "stats";

export type ToolRecordKind = "vision" | "decision";

export interface ToolRecord {
  id: string;
  kind: ToolRecordKind;
  crop: string;
  result: string;
  mode: string;
  created_at: string;
}

export interface ToolRecordPagination {
  has_more: boolean;
  next_cursor: string | null;
}

export interface ToolStatsPayload {
  counts_by_kind: Partial<Record<ToolRecordKind, number>>;
  by_day: Record<string, number>;
  by_day_since: string;
  by_day_days: number;
  top_crops: Array<{ crop: string; total: number }>;
  total_sessions: number;
  total_messages: number;
}

export interface HealthPayload {
  success: boolean;
  app_name: string;
  app_version: string;
  mode: string;
  ai_configured: boolean;
  model_status: string;
  environment: string;
  backend_url: string;
  available_models: string[];
  max_message_length: number;
  requests_per_minute: number;
  upload_max_bytes: number;
  debug: boolean;
  database_path: string;
  allowed_origins: string[];
  warnings: string[];
  error?: string;
}

export interface User {
  id: string;
  username: string;
  display_name: string;
  preferred_model: string;
  created_at: string;
}

export interface SessionItem {
  id: string;
  title: string;
  feature: string;
  model_name: string;
  created_at: string;
  updated_at: string;
  last_message: string;
  is_pinned: boolean;
  pinned_at: string | null;
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  delivery_status?: "pending" | "failed";
  client_request_id?: string;
}

export interface ApiError {
  success: false;
  error: string;
}
