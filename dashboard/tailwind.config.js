// Tailwind v3 does not merge `content` from a preset, and frappe-ui's own list
// covers surfaces this app's globs missed — the experimental CommandPalette
// among them, which is why its padding classes were never generated.
import { readFileSync } from 'node:fs'
import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

// Apps name their sidebar icon in Python, which no content glob scans.
const pluginIcons = JSON.parse(readFileSync(new URL('../commera/sdk/plugin_icons.json', import.meta.url), 'utf8'))

const SPACE = '(0|0\\.5|1|1\\.5|2|2\\.5|3|4|5|6|8|10|12|16)'
const BREAKPOINTS = ['sm', 'md', 'lg']

// The classes promised to plugins, kept whether or not a dashboard screen still uses them. Renaming or
// removing one breaks every plugin that builds against it; the plugin reference lists the same set.
const pluginClasses = [
  { pattern: /^text-ink-[\w-]+$/ },
  { pattern: /^bg-surface-[\w-]+$/ },
  { pattern: /^border-outline-[\w-]+$/ },
  { pattern: /^text-(xs|sm|base|lg|xl|2xl|3xl)(-medium|-semibold)?$/ },
  { pattern: /^text-p-[\w-]+$/ },
  { pattern: /^rounded(-[tblr])?-([1-8]|full|none)$/ },
  { pattern: /^shadow(-(sm|base|md|lg|xl|2xl|none))?$/ },
  { pattern: /^(border|border-[xytbse])$/ },
  { pattern: new RegExp(`^(p|px|py|pt|pb|ps|pe|m|mx|my|mt|mb|ms|me)-${SPACE}$`), variants: BREAKPOINTS },
  { pattern: new RegExp(`^(gap|gap-x|gap-y|space-x|space-y)-${SPACE}$`), variants: BREAKPOINTS },
  { pattern: /^(flex|inline-flex|grid|block|inline-block|hidden|contents)$/, variants: BREAKPOINTS },
  { pattern: /^flex-(row|col|wrap|nowrap|1|none)$/, variants: BREAKPOINTS },
  { pattern: /^(items|justify|self)-(start|end|center|between|stretch|baseline)$/, variants: BREAKPOINTS },
  { pattern: /^(grow|shrink|grow-0|shrink-0)$/, variants: BREAKPOINTS },
  { pattern: /^(grid-cols|col-span)-([1-9]|1[0-2]|full)$/, variants: BREAKPOINTS },
  { pattern: /^w-(full|auto|fit|1\/2|1\/3|2\/3|1\/4|3\/4)$/, variants: BREAKPOINTS },
  { pattern: /^(min-w-0|min-w-full|h-full|min-h-0)$/ },
  { pattern: /^max-w-(xs|sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|full|none)$/ },
  { pattern: /^(truncate|tabular-nums|whitespace-nowrap|whitespace-normal|break-words|break-all)$/ },
  { pattern: /^overflow-(hidden|auto|x-auto|y-auto)$/ },
  { pattern: /^text-(left|center|right|start|end)$/ },
  { pattern: /^(font-normal|font-medium|font-semibold|uppercase|underline)$/ },
]

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  content: [...frappeUIContent, './index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  safelist: [...pluginIcons.map((name) => `lucide-${name}`), ...pluginClasses],
}
