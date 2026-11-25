export function initialsOf(name) {
  const words = String(name ?? "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return "?";
  const letters = words.slice(0, 2).map((word) => Array.from(word)[0]);
  return letters.join("").toUpperCase();
}
