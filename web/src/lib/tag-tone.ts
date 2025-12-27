export type TagTone = "accent" | "warn" | undefined;

export const getTagTone = (tag: string): TagTone => {
  const normalized = tag.toLowerCase();
  if (normalized.includes("lost") || normalized.includes("too expensive")) {
    return "warn";
  }
  if (normalized.includes("potential") || normalized.startsWith("$")) {
    return "accent";
  }
  return undefined;
};
