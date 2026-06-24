/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'dashboard': {
          'bg': '#0f172a',
          'card': '#1e293b',
          'card-hover': '#334155',
          'text': '#f1f5f9',
          'text-muted': '#94a3b8',
          'accent': '#8b5cf6',
          'accent-hover': '#7c3aed',
        }
      }
    },
  },
  plugins: [],
}

