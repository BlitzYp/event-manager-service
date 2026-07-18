import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#212529",
        canvas: "#f4f6f3",
        leaf: { 50: "#eef8e8", 500: "#62b91a", 600: "#4fa800", 700: "#3d8500" },
      },
      boxShadow: { soft: "0 .25rem .9rem rgba(33, 37, 41, 0.09)" },
    },
  },
  plugins: [],
} satisfies Config;
