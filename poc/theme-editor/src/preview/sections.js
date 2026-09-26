// Each renderer stands in for a theme's Jinja section template
// (sections/<type>.html). It receives exactly what the real template would:
// `section` (id, settings, blocks) plus page context and theme settings, and
// wraps output in data attributes the editor uses to select and highlight.
import { COLLECTIONS, PRODUCTS, imageUrl } from '../theme/sample-data.js'
import { APP_BLOCKS, SECTIONS } from '../theme/schemas.js'

const escape = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character])

// render_blocks(section): the Jinja helper equivalent of `content_for 'blocks'`.
function blocks(section, context, renderers) {
  return section.blocks
    .filter((block) => !block.disabled)
    .map((block) => {
      const appBlock = APP_BLOCKS[block.type]
      const inner = appBlock ? renderAppBlock(block, context) : renderers[block.type]?.(block, context) ?? ''
      const name = appBlock ? `${appBlock.app} · ${appBlock.name}` : SECTIONS[section.type].blocks?.[block.type]?.name
      return `<div class="block${appBlock ? ' app-block' : ''}" data-block-id="${block.id}" data-label="${escape(name)}">${inner}</div>`
    })
    .join('')
}

function renderAppBlock(block, { t }) {
  if (block.type === 'print2commera/size_chart') {
    return `<button class="link-button">📏 ${escape(t(block.settings.label))} <span class="muted">(${escape(block.settings.unit)})</span></button>`
  }
  if (block.type === 'print2commera/made_to_order') {
    return `<p class="note">Printed to order · ships in ${Number(block.settings.days)} days</p>`
  }
  return ''
}

const collectionLabel = (value, language) => {
  const collection = COLLECTIONS.find((candidate) => candidate.value === value)
  return collection ? (language === 'ar' ? collection.label_ar : collection.label) : ''
}

const productCards = (products, showPrices) =>
  products
    .map(
      (product) => `<a class="product-card">
        <img src="${product.image}" alt="" />
        <span class="product-name">${escape(product.name)}</span>
        ${showPrices ? `<span class="price">$${product.price}.00</span>` : ''}
      </a>`,
    )
    .join('')

export const RENDERERS = {
  announcement_bar: ({ settings }, { t, language }) => `
    <div class="announcement" style="background:${escape(settings.background)}">
      ${escape(t(settings.text))}${settings.link ? ` · <u>${escape(collectionLabel(settings.link, language))}</u>` : ''}
    </div>`,

  site_header: ({ settings }, { t }) => `
    <header class="site-header${settings.sticky ? ' sticky' : ''}">
      <strong class="logo">${escape(settings.logo_text)}</strong>
      <nav>${COLLECTIONS.slice(0, 3).map((collection) => `<a>${escape(t({ en: collection.label, ar: collection.label_ar }))}</a>`).join('')}</nav>
      <div class="header-icons">${settings.show_search ? '<span>🔍</span>' : ''}<span>🛒</span></div>
    </header>`,

  hero_slider: (section, context) => {
    const slides = section.blocks.filter((block) => !block.disabled)
    return `<div class="hero hero-${escape(section.settings.height)}">
      ${blocks(section, context, {
        slide: ({ settings }, { t }) => `
          <div class="slide" style="background-image:url('${imageUrl(settings.image)}')">
            <div class="slide-copy">
              <h1>${escape(t(settings.heading))}</h1>
              <p>${escape(t(settings.subheading))}</p>
              <a class="button">${escape(t(settings.button_label))}</a>
            </div>
          </div>`,
      })}
      ${slides.length > 1 ? `<div class="dots">${slides.map((_, index) => `<i class="${index ? '' : 'on'}"></i>`).join('')}</div>` : ''}
    </div>`
  },

  collection_list: (section, context) => `
    <div class="container">
      <h2>${escape(context.t(section.settings.heading))}</h2>
      <div class="collection-grid">
        ${blocks(section, context, {
          collection: ({ settings }, { language }) => {
            const collection = COLLECTIONS.find((candidate) => candidate.value === settings.collection) ?? COLLECTIONS[0]
            return `<a class="collection-card" style="background-image:url('${imageUrl(collection.image)}')"><span>${escape(collectionLabel(collection.value, language))}</span></a>`
          },
        })}
      </div>
    </div>`,

  product_grid: ({ settings }, { t }) => {
    const products = PRODUCTS.filter((product) => product.collection === settings.collection)
    const list = [...products, ...PRODUCTS].slice(0, Number(settings.count))
    return `<div class="container">
      <h2>${escape(t(settings.heading))}</h2>
      <div class="product-grid" style="--columns:${Number(settings.columns)}">${productCards(list, settings.show_prices)}</div>
    </div>`
  },

  image_with_text: ({ settings }, { t }) => `
    <div class="container image-with-text${settings.image_position === 'end' ? ' reverse' : ''}">
      <img src="${imageUrl(settings.image)}" alt="" />
      <div>
        <h2>${escape(t(settings.heading))}</h2>
        <p>${escape(t(settings.body))}</p>
        <a class="button">${escape(t(settings.button_label))}</a>
      </div>
    </div>`,

  testimonials: (section, context) => `
    <div class="container">
      <h2>${escape(context.t(section.settings.heading))}</h2>
      <div class="quotes">${blocks(section, context, {
        quote: ({ settings }, { t }) => `<figure><blockquote>“${escape(t(settings.quote))}”</blockquote><figcaption>${escape(settings.author)}</figcaption></figure>`,
      })}</div>
    </div>`,

  newsletter: ({ settings }, { t }) => `
    <div class="newsletter">
      <h2>${escape(t(settings.heading))}</h2>
      <div class="newsletter-form"><input placeholder="you@example.com" /><a class="button">${escape(t(settings.button_label))}</a></div>
    </div>`,

  main_product: (section, context) => {
    const product = PRODUCTS[0]
    return `<div class="container main-product gallery-${escape(section.settings.gallery)}">
      <div class="gallery">
        <img src="${product.image}" alt="" />
        ${section.settings.gallery === 'thumbnails' ? `<div class="thumbs">${PRODUCTS.slice(1, 4).map((item) => `<img src="${item.image}" alt="" />`).join('')}</div>` : ''}
      </div>
      <div class="product-info">${blocks(section, context, {
        title: () => `<h1>${escape(product.name)}</h1>`,
        price: ({ settings }) => `<p class="big-price">$${product.price}.00 ${settings.show_compare ? '<s class="muted">$45.00</s>' : ''}</p>`,
        variant_picker: ({ settings }) =>
          settings.style === 'swatches'
            ? `<div class="sizes">${['S', 'M', 'L', 'XL'].map((size, index) => `<span class="${index === 1 ? 'on' : ''}">${size}</span>`).join('')}</div>`
            : '<select class="select"><option>M</option></select>',
        buy_buttons: ({ settings }) => `<a class="button wide">Add to cart</a>${settings.show_buy_now ? '<a class="button wide ghost">Buy it now</a>' : ''}`,
        description: () => '<p class="muted">Heavyweight cotton, garment-dyed and printed to order in Barcelona.</p>',
      })}</div>
    </div>`
  },

  related_products: ({ settings }, { t }) => `
    <div class="container">
      <h2>${escape(t(settings.heading))}</h2>
      <div class="product-grid" style="--columns:4">${productCards(PRODUCTS.slice(4, 4 + Number(settings.count)), true)}</div>
    </div>`,

  collection_banner: ({ settings }, { language }) => `
    <div class="collection-banner" style="background-image:url('${imageUrl(settings.image)}')">
      <h1>${escape(collectionLabel('t-shirts', language))}</h1>
      ${settings.show_description ? '<p>Soft, heavy, printed when you order.</p>' : ''}
    </div>`,

  main_collection: ({ settings }) => `
    <div class="container main-collection${settings.show_filters ? ' with-filters' : ''}">
      ${settings.show_filters ? '<aside class="filters"><strong>Filter</strong><label>☐ In stock</label><label>☐ Under $30</label><label>☐ Oversized</label></aside>' : ''}
      <div class="product-grid" style="--columns:${Number(settings.columns)}">${productCards(PRODUCTS.slice(0, 9), true)}</div>
    </div>`,

  site_footer: (section, context) => `
    <footer class="site-footer">
      <div class="footer-columns">${blocks(section, context, {
        link_column: ({ settings }, { t }) => `<div><strong>${escape(t(settings.heading))}</strong>${String(settings.links).split('\n').filter(Boolean).map((link) => `<a>${escape(link)}</a>`).join('')}</div>`,
      })}</div>
      <p class="muted">${escape(context.t(section.settings.note))}</p>
    </footer>`,
}

// render_layout(template): every section, in order, wrapped for the editor.
export function renderPage(payload) {
  const t = (value) => (value && typeof value === 'object' ? value[payload.language] || value.en || '' : value ?? '')
  const context = { t, language: payload.language }
  return [...payload.header, ...payload.sections, ...payload.footer]
    .filter((section) => !section.disabled)
    .map((section) => {
      const html = RENDERERS[section.type]?.(section, context) ?? ''
      return `<section class="section" data-section-id="${section.id}" data-label="${escape(SECTIONS[section.type].name)}">${html}</section>`
    })
    .join('')
}
