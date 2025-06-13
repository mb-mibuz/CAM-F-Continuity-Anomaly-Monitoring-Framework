/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'poppins': ['Poppins', 'sans-serif'],
      },
      fontSize: {
        '12': '12px',
        '14': '14px',
        '16': '16px',
        '18': '18px',
      },
      colors: {
        'primary': '#515151',
        'text-gray': '#7C7C7C',
        'text-light': '#C2C2C2',
        'bg-gray': '#D9D9D9',
        'card-gray': '#C4C4C4',
        'error-red': '#EF4444',
        'warning-yellow': '#F59E0B',
      },
      borderWidth: {
        '0.25': '0.25px',
        '0.5': '0.5px',
        '2.5': '2.5px',
      },
      spacing: {
        '30': '30px',
        '90': '90px',
        '262': '262px',
        '357': '357px',
      }
    },
  },
  plugins: [],
}