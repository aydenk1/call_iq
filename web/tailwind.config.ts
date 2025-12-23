import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        muted: "var(--muted)",
        panel: "var(--panel)",
        border: "var(--border)",
        accent: "var(--accent)",
        accent2: "var(--accent-2)",
        tag: "var(--tag)",
      },
      boxShadow: {
        soft: "0 18px 40px rgba(17, 24, 39, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
