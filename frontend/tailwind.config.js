/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#fff8eb',
          100: '#feeac7',
          200: '#fdd28a',
          300: '#fcb44d',
          400: '#fb9a24',
          500: '#f5780b',
          600: '#d95606',
          700: '#b43a09',
          800: '#922d0e',
          900: '#78260f',
        },
      },
    },
  },
  plugins: [],
}
