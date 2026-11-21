/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./client/index.html",
    "./client/src/**/*.{js,ts,jsx,tsx}",
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    screens: {
      xs: "360px",
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1440px",
    },
    extend: {
      colors: {
        body: "var(--color-background-body)",
        surface: "var(--color-background-surface)",
        elevated: "var(--color-background-card)",
        muted: "var(--color-background-muted)",
        border: "var(--color-border)",
        "border-focus": "var(--color-border-emphasized)",
        "text-primary": "var(--color-text-primary)",
        "text-secondary": "var(--color-text-secondary)",
        "text-tertiary": "var(--color-text-disabled)",
        accent: "var(--color-text-accent)",
        positive: "var(--color-success)",
        negative: "var(--color-error)",
        warning: "var(--color-warning)",
        live: "#ef4444",
      },
      fontFamily: {
        heading: "var(--font-family-heading)",
        body: "var(--font-family-body)",
        mono: "var(--font-family-code)",
      },
      borderRadius: {
        sm: "var(--radius-sm, 4px)",
        md: "var(--radius-md, 8px)",
        lg: "var(--radius-lg, 12px)",
        full: "9999px",
      },
    },
  },
  plugins: [],
};
