import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { loadComponent, mount, shell, findNode } from '../helpers/mountVue.js'
import { groupResources, languageTotals, toDoCount } from '../../src/data/translationStatus.js'

const flush = async () => { for (let index = 0; index < 8; index++) await Vue.nextTick() }

test('Languages opens the registered product editor and refreshes work across targets on each opening', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', name: 'StorefrontTranslations', component: shell },
    { path: '/translations/:lang/:resource', name: 'StorefrontTranslationEditor', component: shell },
  ] })
  await router.push('/')
  const overview = Vue.ref(null)
  let loads = 0
  let counts = { fr: { product: { missing: 3, outdated: 2, current: 5 } }, ar: { page: { missing: 1, outdated: 4, current: 0 } } }
  const languages = Vue.ref([{ code: 'en', name: 'English', published: true }, { code: 'fr', name: 'French' }])
  const active = Vue.ref(false)
  const component = loadComponent('components/settings/LanguagesSettings', {
    ...Object.fromEntries(['Alert', 'Button', 'FormControl', 'SettingsBody', 'AddLanguageDialog', 'EmptyState',
      'SettingsPanelHeader', 'SettingsSkeleton'].map((name) => [name, shell])),
    SettingsRow: { props: ['title', 'description'], render() { return Vue.h('section', { title: this.title, description: this.description }, this.$slots.default?.()) } },
    LanguageRow: { props: ['language'], emits: ['translate'], render() { return Vue.h('button', { 'data-language': this.language.code, onClick: () => this.$emit('translate') }) } },
    store: { screen: Vue.ref({}), loadError: Vue.ref(null), loading: Vue.ref(false), languages,
      defaultLanguage: Vue.ref('en'), maxLanguages: Vue.ref(5), isAtLimit: Vue.ref(false), load() {}, mutate() {} },
    useTranslationOverview: () => ({ overview, loadOverview: async () => { loads++; overview.value = { counts } } }),
    languageTotals, toDoCount, useRouter: () => router, languagePrefix: () => '/',
    __: (text, values = []) => text.replace('{0}', values[0]), dialog: {}, toast: {},
  })
  const fixture = mount({ render: () => Vue.h(component, { active: active.value }) })
  try {
    active.value = true
    await flush()
    const row = () => findNode(fixture.root, (node) => node.props.title === 'Translations')
    assert.equal(row().props.description, '10 fields to translate or update')
    const translate = findNode(fixture.root, (node) => node.props['data-language'] === 'fr')
    const navigated = new Promise((resolve) => router.afterEach(resolve))
    translate.props.onClick()
    await navigated
    await flush()
    assert.equal(router.currentRoute.value.name, 'StorefrontTranslationEditor')
    assert.equal(router.currentRoute.value.params.lang, 'fr')
    const registry = [{ type: 'product', label: 'Products' }]
    assert.ok(groupResources(registry).flatMap((group) => group.resources).some((resource) => resource.type === router.currentRoute.value.params.resource))
    active.value = false
    await flush()
    counts = { fr: { product: { missing: 1, outdated: 0, current: 9 } } }
    active.value = true
    await flush()
    assert.equal(loads, 2)
    assert.equal(row().props.description, '1 fields to translate or update')
  } finally { fixture.unmount() }
})

test('mounted CSV dialog reconciles its target when configured languages change', async () => {
  const languages = Vue.ref([{ code: 'fr', name: 'French' }, { code: 'ar', name: 'Arabic' }])
  const component = loadComponent('components/translations/TranslationImportDialog', {
    Button: shell, Dialog: shell,
    FormControl: { props: ['modelValue'], render() { return Vue.h('select', { value: this.modelValue }) } },
    useAdminAction: () => ({}), useAdminRead: () => ({}), useFileUpload: () => ({}), trySubmit() {}, toast: {},
    FrappeResponseError: Error, errorMessage: String, __: (text) => text,
  })
  const fixture = mount({ render: () => Vue.h(component, { open: true, languages: languages.value }) })
  try {
    const target = () => findNode(fixture.root, (node) => node.type === 'select')
    assert.equal(target().props.value, 'fr')
    languages.value = [{ code: 'ar', name: 'Arabic' }, { code: 'en', name: 'English' }]
    await flush()
    assert.equal(target().props.value, 'ar')
    languages.value = []
    await flush()
    const upload = findNode(fixture.root, (node) => node.type === 'button' && node.children.some((child) => child.text === 'Choose CSV file'))
    assert.equal(upload.props.disabled, true)
  } finally { fixture.unmount() }
})

async function pollImport(t, answers) {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  class FrappeResponseError extends Error {}
  const toasts = []
  const statusRequest = {
    error: null,
    async fetch() {
      const answer = answers.shift()
      this.error = answer instanceof Error ? answer : null
      return this.error ? null : answer
    },
  }
  const component = loadComponent('components/translations/TranslationImportDialog', {
    Button: { props: ['loading'], render() { return Vue.h('button', { loading: this.loading }) } },
    Dialog: { render() { return Vue.h('div', this.$slots.default?.()) } }, FormControl: shell, FrappeResponseError, errorMessage: (error) => error.message,
    useAdminAction: () => ({ data: { queued: true, job_id: 'job-1' } }), useAdminRead: () => statusRequest,
    useFileUpload: () => ({ upload: async () => ({ file_url: '/private/files/fr.csv' }) }),
    trySubmit: async () => true, toast: { error: (message) => toasts.push(message) }, __: (text) => text,
  })
  const fixture = mount({ render: () => Vue.h(component, { open: true, languages: [{ code: 'fr', name: 'French' }] }) })
  t.after(() => fixture.unmount())
  const input = findNode(fixture.root, (node) => node.type === 'input')
  input.props.onChange({ target: { files: [{ name: 'fr.csv' }], value: '' } })
  await flush()
  const isLoading = () => findNode(fixture.root, (node) => node.type === 'button').props.loading
  async function tick(milliseconds) {
    t.mock.timers.tick(milliseconds)
    await flush()
  }
  return { isLoading, tick, toasts, statusRequest, FrappeResponseError }
}

test('the CSV dialog keeps polling a background import through network errors, slower each time', async (t) => {
  const offline = new TypeError('Failed to fetch')
  const answers = [offline, offline, { status: 'queued' }, { status: 'done', report: { updated: 1, unchanged: 0, skipped: 0, errors: [] } }]
  const poll = await pollImport(t, answers)
  await poll.tick(2000)
  assert.equal(poll.isLoading(), true)
  await poll.tick(4000)
  assert.equal(answers.length, 2)
  await poll.tick(7999)
  assert.equal(answers.length, 2)
  await poll.tick(1)
  assert.equal(poll.isLoading(), true)
  await poll.tick(2000)
  assert.equal(poll.isLoading(), false)
  assert.deepEqual(poll.toasts, [])
})

test('the CSV dialog caps the poll back-off at 30 seconds', async (t) => {
  const offline = new TypeError('Failed to fetch')
  const answers = [offline, offline, offline, offline, offline, { status: 'done', report: { updated: 1, unchanged: 0, skipped: 0, errors: [] } }]
  const poll = await pollImport(t, answers)
  for (const delay of [2000, 4000, 8000, 16000]) await poll.tick(delay)
  assert.equal(answers.length, 2)
  await poll.tick(29999)
  assert.equal(answers.length, 2)
  await poll.tick(1)
  assert.equal(answers.length, 1)
  await poll.tick(29999)
  assert.equal(poll.isLoading(), true)
  await poll.tick(1)
  assert.equal(poll.isLoading(), false)
  assert.deepEqual(poll.toasts, [])
})

test('the CSV dialog stops polling when the import fails', async (t) => {
  const failed = await pollImport(t, [{ status: 'failed', error: 'The import stopped before it finished.' }])
  await failed.tick(2000)
  assert.equal(failed.isLoading(), false)
  assert.deepEqual(failed.toasts, ['The import stopped before it finished.'])
})

test('the CSV dialog stops polling when the server refuses the poll', async (t) => {
  const answers = []
  const refused = await pollImport(t, answers)
  answers.push(new refused.FrappeResponseError('No such import.'))
  await refused.tick(2000)
  assert.equal(refused.isLoading(), false)
  assert.deepEqual(refused.toasts, ['No such import.'])
})
