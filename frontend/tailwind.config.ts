import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#15201c",
        canvas: "#f3f6f2",
        leaf: { 50: "#effaf3", 500: "#2f8f5b", 600: "#237448", 700: "#1a5b38" },
      },
      boxShadow: { soft: "0 14px 45px rgba(21, 32, 28, 0.09)" },
    },
  },
  plugins: [],
} satisfies Config;

