/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // TOMATO brand green for the sales actions (quote, WhatsApp, send).
        // White text: 7.1:1 on DEFAULT, 5.0:1 on light (dark mode).
        brand: { DEFAULT: "#166534", hover: "#14532d", light: "#15803d" },
      },
    },
  },
  plugins: [],
};
