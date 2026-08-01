export type FeatureKey = "chat" | "vision" | "decision" | "models";

export interface ModelConfig {
  id: string;
  provider: string;
  display_name: string;
  model: string;
  base_url: string;
  masked_key: string;
  is_default: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
  last_verified_at: string | null;
  last_verify_status: string | null;
  last_verify_error_code: string | null;
}

export interface ModelConfigStatus {
  enabled: boolean;
  persistence_enabled: boolean;
  allowed_providers: string[];
  system_model_available: boolean;
  configs: ModelConfig[];
}

export interface HealthPayload {
  success: boolean;
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
  model_config_id: string | null;
  created_at: string;
  updated_at: string;
  last_message: string;
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
