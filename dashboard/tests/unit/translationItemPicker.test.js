import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'

const source = readFileSync(new URL('../../src/components/translations/TranslationItemPicker.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
const render = new Function('Vue', code)(Vue)

async function renderPicker(state) {
  const component = Vue.defineComponent({
    render,
    setup: () => ({
      language: { name: 'French' },
      resource: { label: 'Products', icon: 'lucide-box' },
      resourceMenu: [], searchText: '', results: [], filter: 'todo',
      shownCount: 0, total: 0, items: [], hasMore: false, loading: false,
      loaded: false, loadError: null,
      errorMessage: (error) => error.message,
      ...state,
    }),
  })
  const app = Vue.createSSRApp(component)
  app.config.globalProperties.__ = (text) => text
  app.component('Button', { props: ['label'], render() { return Vue.h('button', this.label) } })
  app.component('Dropdown', { render() { return Vue.h('div', this.$slots.default?.()) } })
  for (const name of ['TextInput', 'TabButtons', 'TranslationStatusDot']) app.component(name, { render: () => null })
  return renderToString(app)
}

test('a failed load renders an error and Retry instead of completion', async () => {
  const html = await renderPicker({ loadError: new Error('offline') })
  assert.match(html, /role="alert"/)
  assert.match(html, /offline/)
  assert.match(html, />Retry<\/button>/)
  assert.doesNotMatch(html, /are up to date/)
})

test('completion appears only after a successful load', async () => {
  assert.doesNotMatch(await renderPicker({}), /are up to date/)
  assert.match(await renderPicker({ loaded: true }), /are up to date/)
})
