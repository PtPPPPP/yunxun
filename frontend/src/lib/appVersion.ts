export function formatAppVersion(value: string): string {
  const version = value.trim();
  if (!version) return "V—";
  return `V${version.replace(/^v/i, "")}`;
}
