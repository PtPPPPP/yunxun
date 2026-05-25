export type FeatureKey = "chat" | "vision" | "decision";

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
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ApiError {
  success: false;
  error: string;
}
