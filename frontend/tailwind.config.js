export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        body: ['Outfit', 'sans-serif'],
      },
      colors: {
        cyber: {
          bg: '#0a0a0c',
          panel: 'rgba(255,255,255,0.03)',
          border: 'rgba(255,255,255,0.08)',
          accent: '#22d3ee', // Cyan
          danger: '#f43f5e', // Rose
          glow: '#4f46e5',   // Indigo
          text: '#ffffff',
          muted: '#9ca3af'
        },
        luxury: {
          bg: '#0f1115',
          panel: '#15181e',
          border: '#2c2e33',
          accent: '#d4af37', // Gold
          danger: '#ff4d4d', // Bright Red
          text: '#f2f2f2',
          muted: '#8c8c8c'
        }
      }
    },
  },
  plugins: [],
}
