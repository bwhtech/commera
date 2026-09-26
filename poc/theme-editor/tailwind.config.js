import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  // The preview page is storefront markup with its own stylesheet, so only the
  // editor is scanned: dashboard tokens never leak into the shop's look.
  content: [...frappeUIContent, './index.html', './src/pages/**/*.vue', './src/editor/**/*.{vue,js}', './src/theme/**/*.js', './src/*.{vue,js}'],
}
