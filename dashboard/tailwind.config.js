// Tailwind v3 does not merge `content` from a preset, and frappe-ui's own list
// covers surfaces this app's globs missed — the experimental CommandPalette
// among them, which is why its padding classes were never generated.
import { readFileSync } from 'node:fs'
import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'
import { readPluginApps, sourceDirOf } from './pluginApps.js'

// Apps name their sidebar icon in Python, which no content glob scans.
const pluginIcons = JSON.parse(readFileSync(new URL('../commera/sdk/plugin_icons.json', import.meta.url), 'utf8'))

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  // Plugins ship no CSS: their classes join this one stylesheet, so a plugin's `hidden` never lands after `sm:block`.
  content: [
    ...frappeUIContent,
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    ...readPluginApps().map((app) => `${sourceDirOf(app)}/**/*.{vue,js,ts}`),
  ],
  safelist: pluginIcons.map((name) => `lucide-${name}`),
  theme: {
    extend: {
      // Named so motion reads `ease-out-strong` instead of a bezier pasted per class. Out is for
      // anything entering or answering a press; in-out for something already on screen moving.
      transitionTimingFunction: {
        'out-strong': 'cubic-bezier(0.23, 1, 0.32, 1)',
        'in-out-strong': 'cubic-bezier(0.77, 0, 0.175, 1)',
      },
    },
  },
}
