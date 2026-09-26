import { APP_BLOCKS, SECTIONS, THEME_SETTINGS } from './schemas.js'

// A theme's default layouts: what a page looks like before the merchant edits
// it. In Commera these ship as files in the theme (templates/index.json…); the
// merchant's edited copies live in the site's database, never in these files.

let counter = 0
export const newId = (prefix) => `${prefix}-${Date.now().toString(36)}${(counter++).toString(36)}`

function defaults(settings) {
  return Object.fromEntries(
    settings.map((setting) => [
      setting.id,
      // Translatable defaults are {en, ar}; copy so edits never touch the schema.
      typeof setting.default === 'object' && setting.default !== null ? { ...setting.default } : setting.default ?? '',
    ]),
  )
}

export function createBlock(sectionType, blockType) {
  const schema = APP_BLOCKS[blockType] ?? SECTIONS[sectionType].blocks[blockType]
  return { id: newId(blockType.split('/').pop()), type: blockType, settings: defaults(schema.settings) }
}

export function createSection(type, blockTypes) {
  const schema = SECTIONS[type]
  const preset = blockTypes ?? schema.presets?.[0]?.blocks ?? []
  return {
    id: newId(type),
    type,
    settings: defaults(schema.settings),
    blocks: preset.map((blockType) => createBlock(type, blockType)),
  }
}

function withOverrides(section, overrides = {}) {
  Object.assign(section.settings, overrides)
  return section
}

export function defaultTheme() {
  const slides = createSection('hero_slider')
  Object.assign(slides.blocks[1].settings, {
    image: 'poster-wall',
    heading: { en: 'Walls worth staring at', ar: 'جدران تستحق التأمل' },
    subheading: { en: 'New poster drop, every Friday.', ar: 'ملصقات جديدة كل جمعة.' },
    link: 'posters',
  })
  const collections = createSection('collection_list')
  collections.blocks.forEach((block, index) => {
    block.settings.collection = ['t-shirts', 'hoodies', 'posters', 'accessories'][index]
  })
  const footer = createSection('site_footer', ['link_column', 'link_column'])
  Object.assign(footer.blocks[1].settings, { heading: { en: 'Help', ar: 'مساعدة' }, links: 'Shipping\nReturns\nContact' })

  return {
    settings: defaults(THEME_SETTINGS.settings),
    groups: {
      header: [createSection('announcement_bar'), createSection('site_header')],
      footer: [createSection('newsletter'), footer],
    },
    templates: {
      index: [
        slides,
        collections,
        createSection('product_grid'),
        createSection('image_with_text'),
        withOverrides(createSection('product_grid'), {
          heading: { en: 'Fresh posters', ar: 'ملصقات جديدة' }, collection: 'posters', count: 4,
        }),
        createSection('testimonials'),
      ],
      product: [
        createSection('main_product', ['title', 'price', 'variant_picker', 'print2commera/size_chart', 'buy_buttons', 'description']),
        createSection('related_products'),
      ],
      collection: [createSection('collection_banner'), createSection('main_collection')],
    },
  }
}
