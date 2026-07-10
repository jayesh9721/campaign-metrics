import type { Config } from "tailwindcss";

const config: Config = {
  // Dark mode follows the OS-level preference (spec requirement), not a manual toggle.
  darkMode: "media",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        surface: "var(--surface)",
        border: "var(--border)",
      },
    },
  },
  plugins: [],
};

export default config;
