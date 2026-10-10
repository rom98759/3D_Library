/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "bp-deep": "#0F2A44",
        "bp-panel": "#16385A",
        "bp-panel2": "#1C4468",
        "bp-ink": "#E9EFF3",
        "bp-ink-dim": "#90A9BE",
        "bp-cyan": "#6FC7DA",
        "bp-yellow": "#F2C14E",
        "bp-green": "#7FBF8F",
        "bp-red": "#E2725B",
      },
      fontFamily: {
        display: ["Oswald", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Work Sans", "sans-serif"],
      },
    },
  },
  plugins: [],
};
