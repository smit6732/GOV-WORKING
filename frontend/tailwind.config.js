/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        gujgov: {
          900: '#0b2545',
          800: '#13315c',
          700: '#1a4480',
          600: '#2563eb',
          accent: '#f97316',
        },
      },
    },
  },
  plugins: [],
}
