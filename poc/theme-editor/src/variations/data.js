import { reactive } from 'vue'

// One set of sample pages for all three variations, so they differ only in UI.
export const STORE_PAGES = [
  { key: 'index', title: 'Home page', icon: 'lucide-home', detail: 'The first page shoppers see' },
  { key: 'product', title: 'Product pages', icon: 'lucide-package', detail: 'One layout for every product' },
  { key: 'collection', title: 'Collection pages', icon: 'lucide-layout-grid', detail: 'One layout for every collection' },
  { key: 'cart', title: 'Cart', icon: 'lucide-shopping-cart', detail: 'Header, footer and colours only' },
]

export const pages = reactive([
  { name: 'summer-sale', title: 'Summer sale', route: '/summer-sale', status: 'Published', kind: 'designed', edited: 'Yesterday' },
  { name: 'about-us', title: 'About us', route: '/about-us', status: 'Published', kind: 'text', edited: 'Last week' },
  { name: 'shipping-policy', title: 'Shipping policy', route: '/shipping-policy', status: 'Published', kind: 'text', edited: '2 months ago' },
  { name: 'winter-lookbook', title: 'Winter lookbook', route: '/winter-lookbook', status: 'Draft', kind: 'designed', edited: '3 days ago' },
])

export const START_OPTIONS = [
  { value: 'blank', label: 'Blank', icon: 'lucide-file', description: 'An empty page' },
  { value: 'template', label: 'Template', icon: 'lucide-layout-template', description: 'Campaign, lookbook, about us' },
  { value: 'ai', label: 'Describe it', icon: 'lucide-sparkles', description: 'Builder drafts it for you' },
]
