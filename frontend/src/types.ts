export type FeatureKey = "decision" | "stats";

export type ToolRecordKind = "decision";

export interface ToolRecord {
  id: string;
  kind: ToolRecordKind;
  crop: string;
  result: string;
  mode: string;
  created_at: string;
}

export interface ToolStatsPayload {
  counts_by_kind: Partial<Record<ToolRecordKind, number>>;
  by_day: Record<string, number>;
  by_day_since: string;
  by_day_days: number;
  top_crops: Array<{ crop: string; total: number }>;
}

export interface HealthPayload {
  success: boolean;
  app_name: string;
  app_version: string;
  environment: string;
  backend_url: string;
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
  created_at: string;
}
