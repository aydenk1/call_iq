import clsx from "clsx";

type TagProps = {
  label: string;
  tone?: "accent" | "warn";
};

export default function Tag({ label, tone }: TagProps) {
  return (
    <span className={clsx("chip", tone === "accent" && "chip-accent", tone === "warn" && "chip-warn")}>
      {label}
    </span>
  );
}
