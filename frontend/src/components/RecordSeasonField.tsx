import { matchRecordSeason, seasonIncludesDate } from "../lib/recordSeason";
import type { PlotSeason } from "../types";

function seasonLabel(season: PlotSeason) {
  return `${season.crop}（${season.started_on ?? "开始日未填"} 至 ${season.ended_on ?? "进行中"}）`;
}

interface RecordSeasonFieldProps {
  seasons: PlotSeason[];
  plotId: string;
  date: string;
  value: string;
  onChange: (value: string) => void;
}

export function RecordSeasonField({ seasons, plotId, date, value, onChange }: RecordSeasonFieldProps) {
  const { plotSeasons, season: matchedSeason, needsChoice } = matchRecordSeason(seasons, plotId, date);

  function selectionHint() {
    if (value === "unassigned") return "本次明确记为未归茬。";
    if (value) {
      const selected = plotSeasons.find((season) => season.id === value);
      if (!selected) return "所选茬次不可用，请重新选择。";
      if (!seasonIncludesDate(selected, date)) {
        return "作业日期不在所选茬次内，请调整日期、选择对应历史茬次或明确选择未归茬。";
      }
      return `本次记入 ${seasonLabel(selected)}。`;
    }
    if (matchedSeason) return `按作业日期匹配：${seasonLabel(matchedSeason)}。`;
    if (needsChoice) return "日期对应的茬次有歧义或开始日未填，请选择具体茬次或未归茬。";
    return "此日期没有匹配茬次，将记为未归茬。";
  }

  return (
    <label className="field">
      <span>所属茬次</span>
      <div className="field-control field-control--select">
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">
            {matchedSeason ? `自动匹配：${seasonLabel(matchedSeason)}` : "按作业日期自动匹配（有歧义请明确选择）"}
          </option>
          <option value="unassigned">未归茬</option>
          {plotSeasons.map((season) => (
            <option key={season.id} value={season.id}>
              {seasonLabel(season)}{season.is_demo ? "【演示】" : ""}
            </option>
          ))}
        </select>
      </div>
      {plotId && <small className="season-hint">{selectionHint()}</small>}
    </label>
  );
}
