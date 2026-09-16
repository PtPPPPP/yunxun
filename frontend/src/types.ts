export type FeatureKey = "decision" | "plots" | "ledger" | "stats";

export type ToolRecordKind = "decision";

export type FarmRecordKind = "播种" | "施肥" | "打药" | "灌溉" | "除草" | "采收" | "其他";

export interface FarmRecord {
  id: string;
  plot_id: string;
  plot_name: string;
  kind: FarmRecordKind;
  happened_on: string;
  crop: string;
  detail: string;
  quantity: string;
  cost: number | null;
  created_at: string;
}

export interface FarmStatsPayload {
  plot_count: number;
  record_count: number;
}

export interface Plot {
  id: string;
  name: string;
  area_mu: number;
  soil_type: string;
  irrigation: string;
  crop: string;
  planted_on: string | null;
  notes: string;
  record_count: number;
  created_at: string;
  updated_at: string;
}

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
