import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { isEmptyResource } from '../../src/data/translationStatus.js'

// Renders a component's template over the given setup state, with frappe-ui stubbed.
async function renderTemplate(path, state) {
  const source = readFileSync(new URL(`../../src/${path}.vue`, import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const app = Vue.createSSRApp({ render, setup: () => state })
  app.config.globalProperties.__ = (text, values = []) => text.replace(/\{(\d+)\}/g, (_match, index) => values[index])
  app.component('Button', {
    props: ['label'],
    render() { return Vue.h('button', [this.label ?? this.$slots.default?.(), this.$slots.suffix?.()]) },
  })
  app.component('Dropdown', {
    props: { matchTriggerWidth: Boolean },
    render() { return Vue.h('div', { 'data-match-width': String(this.matchTriggerWidth) }, this.$slots.default?.()) },
  })
  app.component('TranslationStatusDot', {
    props: ['status'],
    render() { return Vue.h('i', { 'data-dot': this.status }) },
  })
  for (const name of ['TextInput', 'TabButtons', 'FormControl', 'RichTextField', 'StatusBadge', 'Thumb', 'Progress', 'Editor', 'EditorContent']) {
    app.component(name, { render: () => null })
  }
  // Vue's fragment and v-if markers say nothing about what the merchant sees.
  return (await renderToString(app)).replace(/<!--[\s\S]*?-->/g, '')
}

function renderCounts(counts) {
  return renderTemplate('components/translations/TranslationCounts', { counts, isEmptyResource })
}

function renderField(field) {
  return renderTemplate('components/translations/TranslationField', {
    field: { field: 'title', label: 'Title', kind: 'text', source: 'Blue shirt', value: 'قميص', status: 'current', ...field },
    sourceLanguage: { name: 'English' },
    language: { name: 'Arabic' },
    status: field.status ?? 'current',
    isUnsaved: false,
    value: 'قميص',
    inputLabel: 'Title',
    isUploading: false,
  })
}

const picker = {
  disabled: false,
  language: { code: 'ar', name: 'Arabic' },
  resource: { type: 'product', label: 'Products', icon: 'lucide-tag' },
  resourceMenu: [],
  searchText: '',
  results: [],
  filter: 'todo',
  matchingCount: 0,
  total: 0,
  items: [],
  rows: [],
  hasMore: false,
  loading: false,
  loaded: true,
  loadError: null,
}

test('a resource with nothing to translate says so instead of Done', async () => {
  assert.match(await renderCounts({ missing: 0, outdated: 0, current: 0 }), /Nothing to translate/)
  const done = await renderCounts({ missing: 0, outdated: 0, current: 3 })
  assert.match(done, /Done/)
  assert.doesNotMatch(done, /Nothing to translate/)
})

test('an outdated field shows the source it was written against', async () => {
  const html = await renderField({ status: 'outdated', previous_source: 'Blue tee' })
  assert.match(html, /Source changed\./)
  assert.match(html, /Was: “Blue tee”/)
})

test('an outdated field saved before source texts were kept shows only that it changed', async () => {
  const html = await renderField({ status: 'outdated', previous_source: null })
  assert.match(html, /Source changed</)
  assert.doesNotMatch(html, /Was:/)
})

test('a translation whose source is now empty says so', async () => {
  const html = await renderField({ source: '', source_empty: true })
  assert.match(html, /Source is empty/)
  assert.doesNotMatch(html, /Source changed/)
})

test('the resource picker is as wide as its menu, with the chevron after the label', async () => {
  const html = await renderTemplate('components/translations/TranslationItemPicker', picker)
  assert.match(html, /data-match-width="true"/)
  assert.match(html, /aria-label="Resource: Products">Products <span class="lucide-chevron-down ms-auto/)
})

test('a resource with no records says there is nothing to translate', async () => {
  const empty = await renderTemplate('components/translations/TranslationItemPicker', picker)
  assert.match(empty, /Nothing to translate here/)
  const finished = await renderTemplate('components/translations/TranslationItemPicker', { ...picker, total: 4 })
  assert.match(finished, /Products are up to date in Arabic/)
})

test('a record with unsaved edits shows the unsaved dot and what is left to do', async () => {
  const row = (name, status, toDo) => ({ item: { name, title: name }, progress: { toDo }, status })
  const rows = [row('edited', 'unsaved', 1), row('finished-unsaved', 'unsaved', 0), row('outdated', 'outdated', 2), row('done', 'current', 0)]
  const html = await renderTemplate('components/translations/TranslationItemPicker', { ...picker, total: 4, items: rows.map((entry) => entry.item), rows })

  assert.match(html, /data-dot="unsaved"><\/i>1</)
  assert.match(html, /aria-label="Unsaved changes"><i data-dot="unsaved"><\/i><\/span>/)
  assert.match(html, /data-dot="outdated"><\/i>2</)
  assert.match(html, /lucide-check/)
})
