// Tailwind v3 does not merge `content` from a preset, and frappe-ui's own list
// covers surfaces this app's globs missed — the experimental CommandPalette
// among them, which is why its padding classes were never generated.
import { readFileSync } from 'node:fs'
import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

// Apps name their sidebar icon in Python, which no content glob scans.
const extensionIcons = JSON.parse(readFileSync(new URL('../commera/sdk/extension_icons.json', import.meta.url), 'utf8'))

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  content: [...frappeUIContent, './index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  safelist: extensionIcons.map((name) => `lucide-${name}`),
}
