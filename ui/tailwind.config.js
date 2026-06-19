/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      colors: {
        white: "rgb(var(--ui-white-rgb) / <alpha-value>)",
        zinc: {
          50: "rgb(var(--ui-zinc-50) / <alpha-value>)",
          100: "rgb(var(--ui-zinc-100) / <alpha-value>)",
          200: "rgb(var(--ui-zinc-200) / <alpha-value>)",
          300: "rgb(var(--ui-zinc-300) / <alpha-value>)",
          400: "rgb(var(--ui-zinc-400) / <alpha-value>)",
          500: "rgb(var(--ui-zinc-500) / <alpha-value>)",
          600: "rgb(var(--ui-zinc-600) / <alpha-value>)",
          700: "rgb(var(--ui-zinc-700) / <alpha-value>)",
          800: "rgb(var(--ui-zinc-800) / <alpha-value>)",
          900: "rgb(var(--ui-zinc-900) / <alpha-value>)",
          950: "rgb(var(--ui-zinc-950) / <alpha-value>)",
        },
        cyan: {
          50: "rgb(var(--ui-cyan-50) / <alpha-value>)",
          100: "rgb(var(--ui-cyan-100) / <alpha-value>)",
          200: "rgb(var(--ui-cyan-200) / <alpha-value>)",
          300: "rgb(var(--ui-cyan-300) / <alpha-value>)",
          400: "rgb(var(--ui-cyan-400) / <alpha-value>)",
          500: "rgb(var(--ui-cyan-500) / <alpha-value>)",
        },
        sky: {
          100: "rgb(var(--ui-cyan-100) / <alpha-value>)",
          200: "rgb(var(--ui-cyan-200) / <alpha-value>)",
          300: "rgb(var(--ui-cyan-300) / <alpha-value>)",
          400: "rgb(var(--ui-cyan-400) / <alpha-value>)",
          500: "rgb(var(--ui-cyan-500) / <alpha-value>)",
        },
        red: {
          100: "rgb(var(--ui-red-100) / <alpha-value>)",
          200: "rgb(var(--ui-red-200) / <alpha-value>)",
          300: "rgb(var(--ui-red-300) / <alpha-value>)",
          400: "rgb(var(--ui-red-400) / <alpha-value>)",
          500: "rgb(var(--ui-red-500) / <alpha-value>)",
        },
        amber: {
          100: "rgb(var(--ui-amber-100) / <alpha-value>)",
          200: "rgb(var(--ui-amber-200) / <alpha-value>)",
          300: "rgb(var(--ui-amber-300) / <alpha-value>)",
          400: "rgb(var(--ui-amber-400) / <alpha-value>)",
          500: "rgb(var(--ui-amber-500) / <alpha-value>)",
          600: "rgb(var(--ui-amber-600) / <alpha-value>)",
        },
        emerald: {
          100: "rgb(var(--ui-emerald-100) / <alpha-value>)",
          200: "rgb(var(--ui-emerald-200) / <alpha-value>)",
          300: "rgb(var(--ui-emerald-300) / <alpha-value>)",
          400: "rgb(var(--ui-emerald-400) / <alpha-value>)",
          500: "rgb(var(--ui-emerald-500) / <alpha-value>)",
          600: "rgb(var(--ui-emerald-600) / <alpha-value>)",
        },
        violet: {
          100: "rgb(var(--ui-violet-100) / <alpha-value>)",
          200: "rgb(var(--ui-violet-200) / <alpha-value>)",
          300: "rgb(var(--ui-violet-300) / <alpha-value>)",
          400: "rgb(var(--ui-violet-400) / <alpha-value>)",
          500: "rgb(var(--ui-violet-500) / <alpha-value>)",
        },
        orange: {
          100: "rgb(var(--ui-orange-100) / <alpha-value>)",
          200: "rgb(var(--ui-orange-200) / <alpha-value>)",
          300: "rgb(var(--ui-orange-300) / <alpha-value>)",
          500: "rgb(var(--ui-orange-500) / <alpha-value>)",
        },
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
