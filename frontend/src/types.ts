export type FeatureKey = "home" | "decision" | "plots" | "ledger" | "tasks" | "stats" | "account" | "trash";

export type ToolRecordKind = "decision";

export type FarmRecordKind = "播种" | "施肥" | "打药" | "灌溉" | "除草" | "采收" | "其他";

export type EconomicsScope = "all" | "cost" | "revenue" | "missing_cost" | "incomplete_harvest";

export interface EconomicsFilters {
  data_scope?: string;
  plot_id: string;
  season_id: string;
  year: string;
}

export interface FarmRecordFilters {
  data_scope?: string;
  plot_id: string;
  season_id: string;
  economics_scope: EconomicsScope;
  kind: string;
  date_from: string;
  date_to: string;
}

export interface FarmTask {
  is_demo?: boolean;
  id: string;
  plot_id: string | null;
  plot_name: string;
  title: string;
  due_on: string;
  done: boolean;
  done_at: string | null;
  notes: string;
  created_at: string;
}

export interface PlotSeason {
  is_demo?: boolean;
  id: string;
  plot_id: string;
  crop: string;
  started_on: string | null;
  ended_on: string | null;
  active: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface HarvestSafety {
  plot_id: string;
  plot_name: string;
  material: string;
  happened_on: string;
  safe_days: number;
  earliest_harvest_on: string | null;
  days_remaining: number | null;
  in_safe_window: boolean;
}

export interface FarmRecord {
  is_demo?: boolean;
  id: string;
  plot_id: string;
  plot_name: string;
  kind: FarmRecordKind;
  happened_on: string;
  crop: string;
  /** 为空表示未归茬：无法按日期唯一确定茬次，或明确选择未归茬。 */
  season_id: string | null;
  season_crop: string;
  material: string;
  detail: string;
  quantity: string;
  cost: number | null;
  safe_days: number | null;
  earliest_harvest_on: string | null;
  yield_kg: number | null;
  unit_price: number | null;
  created_at: string;
}

export interface PlotEconomics {
  is_demo?: boolean;
  /** 为空表示明确选择未归茬，或记录无法确定茬次归属。 */
  season_id: string | null;
  plot_id: string;
  plot_name: string;
  crop: string;
  started_on: string | null;
  ended_on: string | null;
  area_mu: number;
  record_count: number;
  recorded_cost_count: number;
  missing_cost_count: number;
  harvest_count: number;
  complete_harvest_count: number;
  incomplete_harvest_count: number;
  recorded_yield_count: number;
  total_cost: number;
  total_yield_kg: number;
  total_revenue: number;
  net_revenue: number;
  cost_per_mu: number | null;
  yield_per_mu: number | null;
  revenue_per_mu: number | null;
  net_per_mu: number | null;
}

export interface FarmStatsPayload {
  plot_count: number;
  record_count: number;
}

export interface Plot {
  is_demo?: boolean;
  id: string;
  name: string;
  area_mu: number;
  soil_type: string;
  irrigation: string;
  crop: string;
  planted_on: string | null;
  notes: string;
  record_count: number;
  open_task_count: number;
  /** 进行中的茬次；为空表示这块地当前没种东西（crop 会是最近一茬的作物）。 */
  active_season: { id: string; crop: string; started_on: string | null } | null;
  season_record_count: number;
  harvest_safety: HarvestSafety | null;
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

/**
 * 只声明界面真正会读的字段。接口还返回环境名、后端地址、限流值、数据库路径等
 * 部署细节，但它们不该出现在农户面前（曾经出现过，已清理），所以这里不声明，
 * 免得以后又被顺手接上去。
 */
export interface HealthPayload {
  success: boolean;
  app_name: string;
  app_version: string;
  warnings: string[];
  error?: string;
}

export interface User {
  is_guest?: boolean;
  id: string;
  username: string;
  display_name: string;
  created_at: string;
}

export interface OnboardingStatus {
  plot_done: boolean;
  season_done: boolean;
  record_done: boolean;
  first_plot_id: string | null;
  skipped: boolean;
  demo_loaded: boolean;
  demo_count: number;
}
