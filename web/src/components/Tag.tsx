import { Badge } from "@/components/ui/badge";
import type { TagTone } from "@/lib/tag-tone";

type TagProps = {
  label: string;
  tone?: TagTone;
};

export default function Tag({ label, tone }: TagProps) {
  const variant = tone === "warn" ? "destructive" : tone === "accent" ? "default" : "secondary";

  return <Badge variant={variant}>{label}</Badge>;
}
