import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'

async function renderTemplate(path, state) {
  const source = readFileSync(new URL(`../../src/${path}.vue`, import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const app = Vue.createSSRApp({ render, setup: () => state })
  app.config.globalProperties.__ = (text, values = []) => text.replace(/\{(\d+)\}/g, (_match, index) => values[index])
  const wrapper = (tag) => ({ render() { return Vue.h(tag, this.$attrs, this.$slots.default?.()) } })
  app.component('ListRows', {
    props: ['items'],
    render() { return Vue.h('div', this.items.map((item) => this.$slots.default({ item }))) },
  })
  for (const name of ['List', 'ListHeader', 'ListHeaderCell', 'ListRow', 'ListCell']) app.component(name, wrapper('div'))
  app.component('Button', { props: ['label'], render() { return Vue.h('button', this.label) } })
  app.component('TagMultiSelect', { props: ['label'], render() { return Vue.h('label', this.label) } })
  for (const name of ['TextInput', 'Select']) app.component(name, { props: ['label'], render() { return Vue.h('input', { 'aria-label': this.label }) } })
  for (const name of ['EmptyState', 'ReceiveStockDialog']) app.component(name, { render: () => null })
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

test('product stock shows on hand as a number, not a locked input', async () => {
  const html = await renderTemplate('components/product/ProductStock', {
    ia: { density: 44 },
    rows: [{ id: 'SHIRT-NAV-M', title: 'Navy · M', sku: 'SHIRT-NAV-M', committed: 2, onHand: 25 }],
    receiveOpen: false,
  })

  assert.match(html, />25</)
  assert.doesNotMatch(html, /<input/)
})

test('product organisation offers only what it can change', async () => {
  const html = await renderTemplate('components/product/ProductOrganization', {
    product: { status: 'active', collections: [] },
    layout: 'stacked',
    collectionOptions: [],
    primaryIcon: () => null,
  })

  assert.match(html, /Collections/)
  assert.doesNotMatch(html, /<input/)
})
