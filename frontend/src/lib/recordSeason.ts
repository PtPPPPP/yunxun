import type { PlotSeason } from "../types";

export function seasonIncludesDate(season: PlotSeason, date: string): boolean {
  return (!season.started_on || season.started_on <= date)
    && (!season.ended_on || date <= season.ended_on);
}

export function matchRecordSeason(seasons: PlotSeason[], plotId: string | null, date: string) {
  const plotSeasons = seasons.filter((season) => season.plot_id === plotId);
  const matches = plotSeasons.filter((season) => seasonIncludesDate(season, date));
  // 起始日未知的茬次可以手选，但不能自动归入。
  const season = matches.length === 1 && matches[0].started_on ? matches[0] : undefined;
  return { plotSeasons, season, needsChoice: matches.length > 0 && !season };
}
