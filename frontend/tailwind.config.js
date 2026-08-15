/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F2F3EE",
        ink: "#1F2A24",
        "ink-soft": "#4A5750",
        pine: "#2F5D50",
        "pine-dim": "#3F6E60",
        slate: "#5B6E8C",
        gain: "#3B6B4A",
        loss: "#9C4A3C",
        caution: "#B98A3E",
        line: "#D7D9CE",
      },
      fontFamily: {
        display: ["'Source Serif 4'", "serif"],
        body: ["'IBM Plex Sans'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};
