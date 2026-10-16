import { reactive } from 'vue'

// What Commera knows about Frappe Builder, and every link into it, in one place.
//
// Builder today (frappe/builder 2285abe): /builder/page/:pageId opens a page,
// /builder/page/new creates one. Everything else below — the template, prompt
// and layout parameters, and a component route — is what the proposed Builder
// hooks would add; nothing else in the prototype builds a Builder URL.
export const BUILDER_PATH = '/builder'

export function builderUrl(kind, { name, template, prompt, layout } = {}) {
  if (kind === 'page') return `${BUILDER_PATH}/page/${encodeURIComponent(name)}`
  if (kind === 'new-page') {
    const query = new URLSearchParams()
    if (template) query.set('template', template) // proposed: start from a builder_block_templates entry
    if (prompt) query.set('prompt', prompt) // proposed: hand the prompt to Builder's AI agent
    if (layout) query.set('layout', layout) // proposed: a builder_page_layouts entry
    return `${BUILDER_PATH}/page/new${query.size ? `?${query}` : ''}`
  }
  if (kind === 'component') return `${BUILDER_PATH}/component/${encodeURIComponent(name)}` // proposed route
  if (kind === 'new-component') return `${BUILDER_PATH}/component/new` // proposed route
  throw new Error(`unknown Builder link: ${kind}`)
}

// Builder Pages on this site. `layout: 'commera-theme'` is the proposed
// builder_page_layouts hook: Builder renders the page inside the active
// theme's header and footer, so it looks like the rest of the store.
// Reactive: the layout switch and "New page" change it while the editor is open.
export const BUILDER_PAGES = reactive([
  {
    name: 'summer-sale',
    title: 'Summer sale',
    route: '/en/summer-sale',
    status: 'Published',
    edited: 'Yesterday by Aisha',
    layout: 'commera-theme',
    components: ['Commera · Product grid (Summer sale collection)', 'Countdown banner'],
  },
  {
    name: 'our-story',
    title: 'Our story',
    route: '/en/our-story',
    status: 'Draft',
    edited: '3 days ago by you',
    layout: 'none',
    components: ['Brand story'],
  },
])

// Builder Components a theme section can embed (the "Builder component" section).
export const BUILDER_COMPONENTS = [
  { value: 'countdown-banner', label: 'Countdown banner' },
  { value: 'brand-story', label: 'Brand story' },
  { value: 'lookbook-grid', label: 'Lookbook grid' },
]

// Starting points offered when creating a page (proposed builder_block_templates).
export const BUILDER_TEMPLATES = [
  { value: 'campaign', label: 'Campaign landing', icon: 'lucide-megaphone', description: 'Hero, countdown, product grid' },
  { value: 'lookbook', label: 'Lookbook', icon: 'lucide-images', description: 'Editorial images with shoppable products' },
  { value: 'about', label: 'About us', icon: 'lucide-heart-handshake', description: 'Story, team, values' },
]
