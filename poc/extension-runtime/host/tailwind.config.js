import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'
import { CURATED_ICONS } from './src/extension-api/icons.js'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  content: [...frappeUIContent, './index.html', './src/**/*.{vue,js}'],
  // Extension icons arrive as data at runtime, so Tailwind never sees them in
  // source. The curated set is compiled in up front; anything else is refused
  // by the kit's class check.
  safelist: CURATED_ICONS.map((name) => `lucide-${name}`),
}
