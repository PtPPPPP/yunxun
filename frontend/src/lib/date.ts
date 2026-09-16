/** 本地日期工具：农事日期都按本机时区的 YYYY-MM-DD 处理，不走 UTC。 */

export function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function addDays(isoDate: string, days: number): string {
  const base = new Date(`${isoDate}T00:00:00`);
  base.setDate(base.getDate() + days);
  return `${base.getFullYear()}-${String(base.getMonth() + 1).padStart(2, "0")}-${String(base.getDate()).padStart(2, "0")}`;
}

export function diffDays(fromIso: string, toIso: string): number {
  const from = new Date(`${fromIso}T00:00:00`).getTime();
  const to = new Date(`${toIso}T00:00:00`).getTime();
  return Math.round((to - from) / 86400000);
}

export function formatDate(isoDate: string): string {
  const [year, month, date] = isoDate.split("-");
  return `${year}/${Number(month)}/${Number(date)}`;
}
