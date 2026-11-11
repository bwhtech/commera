import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { useTranslationSave } from '../../src/data/translationEditorState.js'

async function renderTemplate(path, state) {
  const source = readFileSync(new URL(`../../src/${path}.vue`, import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const app = Vue.createSSRApp({ render, setup: () => state })
  app.config.globalProperties.__ = (text) => text
  for (const name of ['Button', 'FormControl', 'TextInput', 'TabButtons']) {
    app.component(name, {
      props: ['disabled', 'label', 'options'],
      render() { return Vue.h('button', { disabled: this.disabled || this.options?.every((option) => option.disabled) }, this.label ?? this.$slots.default?.()) },
    })
  }
  for (const name of ['Dropdown', 'AppPageHeader', 'PageBody', 'ScrollArea', 'RouterLink']) {
    app.component(name, { render() { return Vue.h('div', [this.$slots.title?.(), this.$slots.actions?.(), this.$slots.default?.()]) } })
  }
  for (const name of ['Badge', 'StatusBadge', 'TranslationStatusDot', 'Thumb', 'TranslationItemPicker', 'TranslationRecord']) {
    app.component(name, { render: () => null })
  }
  app.directive('scroll-fade', {})
  return renderToString(app)
}

test('inputs and navigation render disabled throughout a deferred save', async () => {
  let settle
  const response = new Promise((resolve) => { settle = resolve })
  const state = useTranslationSave({ title: 'draft' }, Vue.ref('ar/product'))
  const saving = state.save(() => response, async () => {})
  const disabled = state.saving.value
  const field = await renderTemplate('components/translations/TranslationField', {
    disabled, field: { kind: 'text', label: 'Title' }, sourceLanguage: {}, language: {},
    status: 'unsaved', isUnsaved: true, value: 'draft', inputLabel: 'Title',
  })
  assert.match(field, /<button disabled/)
  const picker = {
    disabled, resource: { label: 'Products' }, resourceMenu: [], searchText: '',
    shownCount: 1, total: 1, items: [{ name: 'one' }], selectedName: 'one',
    filter: 'todo', hasMore: true, loading: false, loaded: true, loadError: null,
  }
  for (const searchText of ['', 'search']) {
    const html = await renderTemplate('components/translations/TranslationItemPicker', {
      ...picker, searchText, results: [{ resource: 'product', records: [{ name: 'one' }] }],
    })
    assert.doesNotMatch(html, /<button(?! disabled)/)
  }
  const editor = await renderTemplate('pages/storefront/TranslationEditor', {
    saving: disabled, busy: disabled, language: { name: 'Arabic' }, languageMenu: [], dirtyCount: 1,
    overviewLoaded: true, overview: {}, resource: {}, isMobile: false,
    selectedName: '', selectedItem: null, recordError: null, list: { items: {}, total: {}, toDoCount: {}, nextCursor: {}, loading: {}, loaded: {}, loadError: {} },
  })
  assert.doesNotMatch(editor, /<button(?! disabled)/)
  settle(null)
  await saving
  assert.equal(state.saving.value, false)
})
