import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Secondary text: helper copy, counts, inactive links.
        muted: "var(--muted-foreground)",
        // Least important text: timestamps, placeholders.
        "muted-subtle": "var(--muted-subtle)",
        interactive: "var(--interactive)",
        disabled: "var(--disabled)",
        // Fills and large surfaces.
        accent: "var(--accent)",
        // Accent for text and icons, contrast-safe in both themes.
        "accent-text": "var(--accent-text)",
        secondary: "var(--secondary)",
        // Fills tuned to carry readable label text.
        "accent-solid": "var(--accent-solid)",
        "secondary-solid": "var(--secondary-solid)",
        "on-accent": "var(--on-accent)",
        // Gradient stops, split by surface fill vs. gradient text.
        "gradient-from": "var(--gradient-from)",
        "gradient-to": "var(--gradient-to)",
        "gradient-text-from": "var(--gradient-text-from)",
        "gradient-text-to": "var(--gradient-text-to)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        "card-bg": "var(--card-bg)",
        "card-hover": "var(--card-hover)",
        highlight: "var(--highlight)",
        success: "var(--success)",
        warning: "var(--warning)",
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
    darkMode: 'class',
  },
  plugins: [],
};
export default config;
