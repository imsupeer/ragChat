import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}', './hooks/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0f0f11',
        panel: '#17171a',
        border: '#2a2a2e',
        user: '#2b6ce6',
        assistant: '#1c1c20',
        muted: '#9ca3af',
      },
    },
  },
  plugins: [],
};

export default config;
