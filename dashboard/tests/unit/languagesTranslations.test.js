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
    useAdminAction: () => ({}), useFileUpload: () => ({}), trySubmit() {}, toast: {}, __: (text) => text,
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
