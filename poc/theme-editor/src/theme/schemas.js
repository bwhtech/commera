// The section schemas a theme ships. In Commera each is a sibling JSON file
// next to its Jinja template (sections/hero_slider.html + hero_slider.json);
// here they are one module so the editor and the preview can both import them.
//
// Setting types map onto Frappe docfield types so the real editor can reuse
// SettingsFieldControl: text → Data, textarea → Small Text, check → Check,
// select → Select, range → Int, color → Color, image → Attach Image,
// collection / product → Link. `translatable` values are stored as {en, ar}.

const heading = (label = 'Heading', fallback = '') => ({
  id: 'heading', type: 'text', label, translatable: true, default: fallback,
})

export const THEME_SETTINGS = {
  name: 'Theme settings',
  icon: 'lucide-palette',
  settings: [
    { id: 'accent', type: 'color', label: 'Accent colour', default: '#ea580c' },
    { id: 'text', type: 'color', label: 'Text colour', default: '#1c1917' },
    { id: 'background', type: 'color', label: 'Background', default: '#fffbf5' },
    { id: 'heading_font', type: 'select', label: 'Heading font', options: 'fonts', default: 'Inter' },
    { id: 'radius', type: 'range', label: 'Corner radius', min: 0, max: 24, step: 2, unit: 'px', default: 12 },
  ],
}

export const SECTIONS = {
  announcement_bar: {
    name: 'Announcement bar',
    icon: 'lucide-megaphone',
    groups: ['header'],
    settings: [
      { id: 'text', type: 'text', label: 'Text', translatable: true, default: { en: 'Free shipping over $50', ar: 'شحن مجاني للطلبات فوق ٥٠$' } },
      { id: 'link', type: 'collection', label: 'Link to collection' },
      { id: 'background', type: 'color', label: 'Background', default: '#1c1917' },
    ],
  },
  site_header: {
    name: 'Header',
    icon: 'lucide-panel-top',
    groups: ['header'],
    static: true,
    settings: [
      { id: 'logo_text', type: 'text', label: 'Store name', default: 'Summer & Co' },
      { id: 'show_search', type: 'check', label: 'Show search', default: true },
      { id: 'sticky', type: 'check', label: 'Stick to top on scroll', default: true },
    ],
  },
  hero_slider: {
    name: 'Hero slider',
    icon: 'lucide-gallery-horizontal',
    settings: [
      { id: 'height', type: 'select', label: 'Height', options: [
        { value: 'small', label: 'Small' }, { value: 'medium', label: 'Medium' }, { value: 'large', label: 'Large' },
      ], default: 'large' },
      { id: 'autoplay', type: 'check', label: 'Autoplay slides', default: true },
    ],
    blocks: {
      slide: {
        name: 'Slide',
        icon: 'lucide-image',
        settings: [
          { id: 'image', type: 'image', label: 'Image', default: 'summer-beach' },
          heading('Heading', { en: 'Made for long days', ar: 'صُنع للأيام الطويلة' }),
          { id: 'subheading', type: 'text', label: 'Subheading', translatable: true, default: { en: 'Printed to order, shipped in days.', ar: 'تُطبع عند الطلب وتُشحن خلال أيام.' } },
          { id: 'button_label', type: 'text', label: 'Button label', translatable: true, default: { en: 'Shop now', ar: 'تسوّق الآن' } },
          { id: 'link', type: 'collection', label: 'Button links to', default: 't-shirts' },
        ],
      },
    },
    max_blocks: 5,
    presets: [{ blocks: ['slide', 'slide'] }],
  },
  collection_list: {
    name: 'Collection list',
    icon: 'lucide-layout-grid',
    settings: [heading('Heading', { en: 'Shop by collection', ar: 'تسوّق حسب المجموعة' })],
    blocks: {
      collection: {
        name: 'Collection',
        icon: 'lucide-folder',
        settings: [{ id: 'collection', type: 'collection', label: 'Collection', default: 'hoodies' }],
      },
    },
    max_blocks: 6,
    presets: [{ blocks: ['collection', 'collection', 'collection', 'collection'] }],
  },
  product_grid: {
    name: 'Featured products',
    icon: 'lucide-shopping-bag',
    settings: [
      heading('Heading', { en: 'Best picks', ar: 'الأكثر اختيارًا' }),
      { id: 'collection', type: 'collection', label: 'Collection', default: 't-shirts' },
      { id: 'count', type: 'range', label: 'Products to show', min: 2, max: 12, step: 1, default: 8 },
      { id: 'columns', type: 'range', label: 'Columns on desktop', min: 2, max: 5, step: 1, default: 4 },
      { id: 'show_prices', type: 'check', label: 'Show prices', default: true },
    ],
  },
  image_with_text: {
    name: 'Image with text',
    icon: 'lucide-image-plus',
    settings: [
      { id: 'image', type: 'image', label: 'Image', default: 'workshop' },
      { id: 'image_position', type: 'select', label: 'Image position', options: [
        { value: 'start', label: 'Start' }, { value: 'end', label: 'End' },
      ], default: 'start' },
      heading('Heading', { en: 'Printed when you order', ar: 'نطبعها عندما تطلب' }),
      { id: 'body', type: 'textarea', label: 'Text', translatable: true, default: { en: 'Every piece is made for you, so nothing sits in a warehouse.', ar: 'كل قطعة تُصنع لك، فلا شيء يبقى في المستودع.' } },
      { id: 'button_label', type: 'text', label: 'Button label', translatable: true, default: { en: 'Our story', ar: 'قصتنا' } },
    ],
  },
  testimonials: {
    name: 'Testimonials',
    icon: 'lucide-quote',
    settings: [heading('Heading', { en: 'What customers say', ar: 'ماذا يقول عملاؤنا' })],
    blocks: {
      quote: {
        name: 'Quote',
        icon: 'lucide-message-square-quote',
        settings: [
          { id: 'quote', type: 'textarea', label: 'Quote', translatable: true, default: { en: 'Softest tee I own. Arrived in four days.', ar: 'أنعم تيشيرت أملكه. وصل خلال أربعة أيام.' } },
          { id: 'author', type: 'text', label: 'Author', default: 'Maya R.' },
        ],
      },
    },
    max_blocks: 6,
    presets: [{ blocks: ['quote', 'quote', 'quote'] }],
  },
  newsletter: {
    name: 'Newsletter',
    icon: 'lucide-mail',
    settings: [
      heading('Heading', { en: 'Get new drops first', ar: 'كن أول من يعرف بالجديد' }),
      { id: 'button_label', type: 'text', label: 'Button label', translatable: true, default: { en: 'Subscribe', ar: 'اشترك' } },
    ],
  },
  main_product: {
    name: 'Product information',
    icon: 'lucide-package',
    templates: ['product'],
    // The page's main section: it can be reordered among the page's sections
    // but never removed, because the page has no purpose without it.
    static: true,
    settings: [
      { id: 'gallery', type: 'select', label: 'Gallery layout', options: [
        { value: 'stacked', label: 'Stacked' }, { value: 'thumbnails', label: 'Thumbnails' },
      ], default: 'thumbnails' },
    ],
    blocks: {
      title: { name: 'Title', icon: 'lucide-heading', settings: [] },
      price: { name: 'Price', icon: 'lucide-tag', settings: [{ id: 'show_compare', type: 'check', label: 'Show compare-at price', default: true }] },
      variant_picker: { name: 'Variant picker', icon: 'lucide-swatch-book', settings: [{ id: 'style', type: 'select', label: 'Style', options: [{ value: 'swatches', label: 'Swatches' }, { value: 'dropdown', label: 'Dropdown' }], default: 'swatches' }] },
      buy_buttons: { name: 'Buy buttons', icon: 'lucide-shopping-cart', settings: [{ id: 'show_buy_now', type: 'check', label: 'Show "Buy now"', default: true }] },
      description: { name: 'Description', icon: 'lucide-align-left', settings: [] },
    },
    // `@app`: app blocks may be placed in this section (see APP_BLOCKS).
    accepts_apps: true,
  },
  related_products: {
    name: 'Related products',
    icon: 'lucide-layers',
    templates: ['product'],
    settings: [
      heading('Heading', { en: 'You may also like', ar: 'قد يعجبك أيضًا' }),
      { id: 'count', type: 'range', label: 'Products to show', min: 2, max: 8, step: 1, default: 4 },
    ],
  },
  collection_banner: {
    name: 'Collection banner',
    icon: 'lucide-rectangle-horizontal',
    templates: ['collection'],
    settings: [
      { id: 'image', type: 'image', label: 'Image', default: 'studio-tees' },
      { id: 'show_description', type: 'check', label: 'Show description', default: true },
    ],
  },
  main_collection: {
    name: 'Product grid',
    icon: 'lucide-grid-3x3',
    templates: ['collection'],
    static: true,
    settings: [
      { id: 'columns', type: 'range', label: 'Columns on desktop', min: 2, max: 5, step: 1, default: 3 },
      { id: 'show_filters', type: 'check', label: 'Show filters', default: true },
    ],
  },
  site_footer: {
    name: 'Footer',
    icon: 'lucide-panel-bottom',
    groups: ['footer'],
    static: true,
    settings: [
      { id: 'note', type: 'text', label: 'Footer note', translatable: true, default: { en: '© 2026 Summer & Co. Printed with care.', ar: '© ٢٠٢٦ سمر آند كو. طُبع بعناية.' } },
    ],
    blocks: {
      link_column: {
        name: 'Link column',
        icon: 'lucide-list',
        settings: [
          heading('Heading', { en: 'Shop', ar: 'تسوّق' }),
          { id: 'links', type: 'textarea', label: 'Links (one per line)', default: 'T-shirts\nHoodies\nPosters' },
        ],
      },
    },
    max_blocks: 4,
  },
}

// App blocks come from installed apps' extension registries, not the theme.
// A section opts in with `accepts_apps`; the theme never names a specific app.
export const APP_BLOCKS = {
  'print2commera/size_chart': {
    app: 'Printful',
    name: 'Size chart',
    icon: 'lucide-ruler',
    settings: [
      { id: 'unit', type: 'select', label: 'Unit', options: [{ value: 'cm', label: 'Centimetres' }, { value: 'in', label: 'Inches' }], default: 'cm' },
      { id: 'label', type: 'text', label: 'Link label', translatable: true, default: { en: 'Size chart', ar: 'جدول المقاسات' } },
    ],
  },
  'print2commera/made_to_order': {
    app: 'Printful',
    name: 'Made-to-order note',
    icon: 'lucide-printer',
    settings: [
      { id: 'days', type: 'range', label: 'Production days', min: 1, max: 10, step: 1, default: 3 },
    ],
  },
}

export const TEMPLATES = [
  { value: 'index', label: 'Home page', icon: 'lucide-home' },
  { value: 'product', label: 'Product', icon: 'lucide-package' },
  { value: 'collection', label: 'Collection', icon: 'lucide-layout-grid' },
]

export function schemaFor(node) {
  if (!node) return null
  if (node.kind === 'theme') return THEME_SETTINGS
  if (node.kind === 'section') return SECTIONS[node.type]
  if (node.kind === 'block') {
    return APP_BLOCKS[node.type] ?? SECTIONS[node.sectionType]?.blocks?.[node.type]
  }
  return null
}

// Sections the merchant may add to a given place on a given template.
export function addableSections(place, template) {
  return Object.entries(SECTIONS)
    .filter(([, schema]) => !schema.static)
    .filter(([, schema]) => (place === 'template' ? !schema.groups : schema.groups?.includes(place)))
    .filter(([, schema]) => place !== 'template' || !schema.templates || schema.templates.includes(template))
    .map(([type, schema]) => ({ type, ...schema }))
}
