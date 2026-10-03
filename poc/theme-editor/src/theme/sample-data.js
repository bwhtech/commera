// Stand-in store data. In Commera these come from Item Group, Style Attribute
// Variant and File records; the preview's section controllers would query them.

// Placeholder artwork as inline SVG, so the prototype needs no network.
function artwork(label, from, to) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/>
    </linearGradient></defs>
    <rect width="800" height="600" fill="url(#g)"/>
    <text x="776" y="578" font-family="sans-serif" font-size="22" fill="rgba(255,255,255,.7)" text-anchor="end">${label}</text>
  </svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

export const IMAGES = [
  { value: 'summer-beach', label: 'Summer beach', url: artwork('Summer beach', '#f59e0b', '#ef4444') },
  { value: 'studio-tees', label: 'Studio tees', url: artwork('Studio tees', '#0ea5e9', '#6366f1') },
  { value: 'street-hoodie', label: 'Street hoodie', url: artwork('Street hoodie', '#111827', '#4b5563') },
  { value: 'poster-wall', label: 'Poster wall', url: artwork('Poster wall', '#10b981', '#0f766e') },
  { value: 'workshop', label: 'Workshop', url: artwork('Workshop', '#a855f7', '#ec4899') },
]

export const imageUrl = (value) => IMAGES.find((image) => image.value === value)?.url ?? IMAGES[0].url

export const COLLECTIONS = [
  { value: 't-shirts', label: 'T-shirts', label_ar: 'تيشيرتات', image: 'studio-tees' },
  { value: 'hoodies', label: 'Hoodies', label_ar: 'هوديز', image: 'street-hoodie' },
  { value: 'posters', label: 'Posters', label_ar: 'ملصقات', image: 'poster-wall' },
  { value: 'accessories', label: 'Accessories', label_ar: 'إكسسوارات', image: 'workshop' },
]

const PALETTE = [
  ['#f97316', '#fb923c'], ['#0ea5e9', '#38bdf8'], ['#111827', '#374151'], ['#16a34a', '#4ade80'],
  ['#9333ea', '#c084fc'], ['#e11d48', '#fb7185'], ['#ca8a04', '#facc15'], ['#0d9488', '#2dd4bf'],
]

export const PRODUCTS = [
  'Sunset Tee', 'Wave Tee', 'Night Hoodie', 'Forest Hoodie', 'Neon Poster', 'Coral Poster',
  'Canvas Tote', 'Dad Hat', 'Stripe Tee', 'Tide Poster', 'Ember Hoodie', 'Linen Cap',
].map((name, index) => ({
  name,
  price: 18 + ((index * 7) % 30),
  collection: COLLECTIONS[index % COLLECTIONS.length].value,
  image: artwork(name, ...PALETTE[index % PALETTE.length]),
}))

export const FONTS = [
  { value: 'Inter', label: 'Inter' },
  { value: 'Georgia', label: 'Georgia (serif)' },
  { value: 'Space Grotesk', label: 'Space Grotesk' },
]
