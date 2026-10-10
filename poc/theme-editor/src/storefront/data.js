import { reactive } from 'vue'

// One site's storefront, as the dashboard would load it. Themes are the core:
// exactly one is live; the rest are drafts. A theme is built either with
// sections (edited in the theme editor) or in Frappe Builder (each of its
// pages is a Builder page). Content pages belong to the store, not a theme,
// and are rendered by whichever theme is live.
export const themes = reactive([
  { name: 'summer_theme', title: 'Summer', kind: 'sections', source: 'Commera', live: true, saved: 'Saved today', colours: ['#f59e0b', '#ef4444'] },
  { name: 'shop_default_theme', title: 'Shop Default', kind: 'sections', source: 'Commera', saved: 'Never customized', colours: ['#0ea5e9', '#6366f1'] },
  { name: 'atelier_theme', title: 'Atelier', kind: 'sections', source: 'Atelier Themes app', saved: 'Never customized', colours: ['#111827', '#6b7280'] },
])

// The pages a Builder theme is made of. Creating a Builder theme creates one
// empty Builder page per entry; `required` ones must be designed to publish.
export const BUILDER_THEME_PAGES = [
  { key: 'chrome', title: 'Header & footer', icon: 'lucide-panels-top-left', detail: 'Shared by every page, including your content pages', required: true },
  { key: 'home', title: 'Home page', icon: 'lucide-home', detail: 'The first page shoppers see', required: true },
  { key: 'product', title: 'Product page', icon: 'lucide-package', detail: 'One design for every product; product data fills it in', required: true },
  { key: 'collection', title: 'Collection page', icon: 'lucide-layout-grid', detail: 'One design for every collection', required: true },
  { key: 'page', title: 'Content page', icon: 'lucide-file-text', detail: 'How your text pages look; a "Page content" block shows the text', required: true },
  { key: 'cart', title: 'Cart', icon: 'lucide-shopping-cart', detail: 'Optional: the default cart uses your header, footer and colours', required: false },
]

// Page templates a content page can choose from, per theme ("Theme template"
// on Shopify). Sections themes ship them; a Builder theme has its Content page.
export const PAGE_TEMPLATES = {
  summer_theme: [
    { value: 'page', label: 'Default page' },
    { value: 'page.contact', label: 'Contact page (with form)' },
    { value: 'page.faq', label: 'FAQ page (collapsible answers)' },
  ],
}

export const contentPages = reactive([
  { name: 'about-us', title: 'About us', visible: true, template: 'page', updated: 'Last week', content: '<h2>Made slowly, on purpose</h2><p>We started as three friends and one print shop, with a rule: nothing gets made until someone wants it.</p><p>Every tee, hoodie and poster is printed when you order it, so nothing sits in a warehouse.</p>', content_ar: '<h2>صُنع ببطء، عن قصد</h2><p>بدأنا كثلاثة أصدقاء ومطبعة واحدة.</p>' },
  { name: 'shipping-policy', title: 'Shipping policy', visible: true, template: 'page', updated: '2 months ago', content: '<p>Orders are printed within 3 working days and ship with tracking.</p>', content_ar: '' },
  { name: 'faq', title: 'FAQ', visible: true, template: 'page.faq', updated: '1 month ago', content: '<h3>How long does printing take?</h3><p>Three working days.</p>', content_ar: '' },
  { name: 'contact', title: 'Contact us', visible: false, template: 'page.contact', updated: 'Yesterday', content: '<p>Write to us any time; we answer within a day.</p>', content_ar: '' },
])

export const liveTheme = () => themes.find((theme) => theme.live)
export const templatesFor = (theme) =>
  theme.kind === 'builder' ? [{ value: 'page', label: 'Content page (designed in Builder)' }] : PAGE_TEMPLATES[theme.name] ?? PAGE_TEMPLATES.summer_theme
