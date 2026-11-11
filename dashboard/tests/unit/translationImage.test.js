import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { loadComponent, mount, shell, findNode } from '../helpers/mountVue.js'
import { uploadTranslationImage } from '../../src/data/translationImage.js'
import * as status from '../../src/data/translationStatus.js'
import * as editorState from '../../src/data/translationEditorState.js'

const flush = async () => { for (let index = 0; index < 12; index++) await Vue.nextTick() }

function editorFixture() {
  let resolveUpload
  let rejectUpload
  const response = new Promise((resolve, reject) => { resolveUpload = resolve; rejectUpload = reject })
  const errors = []
  const common = Object.fromEntries([
    'Button', 'FormControl', 'Progress', 'Editor', 'EditorContent', 'RichTextKit', 'RichTextField',
    'StatusBadge', 'Thumb', 'Badge', 'Dropdown', 'LoadingText', 'ScrollArea', 'AppPageHeader', 'PageBody', 'EmptyState',
  ].map((name) => [name, shell]))
  common.__ = (text) => text
  common.toast = { error: (message) => errors.push(message), success() {} }
  const field = loadComponent('components/translations/TranslationField', {
    ...common, uploadTranslationImage, useFileUpload: () => ({ upload: () => response, progress: Vue.ref(35) }),
  })
  const record = loadComponent('components/translations/TranslationRecord', {
    ...common, TranslationField: field, ...status,
  })
  const route = Vue.reactive({ params: { lang: 'fr', resource: 'product' }, query: { record: 'A' } })
  const guards = []
  const router = {
    replace(target) { if (guards.every((guard) => guard({ ...route, ...target }) !== false)) route.query = target.query },
    push() {},
  }
  const items = ['A', 'B'].map((name) => ({
    name, title: name, fields: [{ field: 'image', label: 'Image', kind: 'image', source: '/source.png', value: '/files/old.png', status: 'outdated' }],
  }))
  const overview = Vue.ref({
    languages: [{ code: 'fr', name: 'French' }], source: { name: 'English' },
    resources: [{ type: 'product', label: 'Products' }], counts: { fr: {} },
  })
  const saves = []
  const component = loadComponent('pages/storefront/TranslationEditor', {
    ...common, ...status, ...editorState, window: {},
    TranslationRecord: record,
    TranslationItemPicker: {
      props: ['disabled'], emits: ['select'],
      render() { return Vue.h('button', { 'data-record': 'B', disabled: this.disabled, onClick: () => this.$emit('select', 'B') }, 'B') },
    },
    useRoute: () => route, useRouter: () => router,
    onBeforeRouteLeave() {}, onBeforeRouteUpdate: (guard) => guards.push(guard),
    useEventListener() {}, useIsMobile: () => Vue.ref(false), onSettingsClose() {}, openSettings() {},
    confirmLeave: async () => true, errorMessage: String,
    useTranslationOverview: () => ({ overview, loadOverview: async () => overview.value }),
    getItems() {}, saveTranslations: async (...args) => { saves.push(args); return 1 },
    useTranslationItems: () => ({
      items: Vue.ref(items), total: Vue.ref(2), toDoCount: Vue.ref(0), nextCursor: Vue.ref(null),
      loading: Vue.ref(false), loaded: Vue.ref(true), loadError: Vue.ref(null),
      refresh: async () => items,
    }),
  })
  const mounted = mount(component)
  return { ...mounted, route, saves, errors, resolveUpload, rejectUpload }
}

for (const action of ['switch', 'save', 'failure']) {
  test(`mounted editor holds navigation and Save during upload: ${action}`, async () => {
    const fixture = editorFixture()
    try {
      await flush()
      const confirm = findNode(fixture.root, (node) => node.type === 'button' && node.children.some((child) => child.text === 'Still correct'))
      confirm.props.onClick()
      await flush()
      const initialSave = findNode(fixture.root, (node) => node.type === 'button' && node.children.some((child) => child.text === 'Save'))
      assert.equal(initialSave.props.disabled, false)
      const input = findNode(fixture.root, (node) => node.type === 'input' && node.props.type === 'file')
      const uploading = input.props.onChange({ target: { files: [{ name: 'A.png' }], value: 'A.png' } })
      await flush()
      const select = findNode(fixture.root, (node) => node.props['data-record'] === 'B')
      const save = findNode(fixture.root, (node) => node.type === 'button' && node.children.some((child) => child.text === 'Save'))
      assert.equal(select.props.disabled, true)
      assert.equal(save.props.disabled, true)
      assert.ok(findNode(fixture.root, (node) => node.props.role === 'status'))
      // Calling handlers also exercises their guards, independently of the disabled buttons.
      select.props.onClick()
      save.props.onClick()
      assert.equal(fixture.route.query.record, 'A')
      assert.equal(fixture.saves.length, 0)
      if (action === 'failure') fixture.rejectUpload(new Error('Upload failed'))
      else fixture.resolveUpload({ file_url: '/files/A.png' })
      await uploading
      await flush()
      assert.equal(select.props.disabled, false)
      if (action === 'failure') {
        assert.equal(fixture.errors.length, 1)
        select.props.onClick()
        await flush()
        assert.equal(fixture.route.query.record, 'B')
        assert.equal(save.props.disabled, false)
      } else {
        assert.equal(save.props.disabled, false)
        if (action === 'switch') {
          select.props.onClick()
          await flush()
          assert.equal(fixture.route.query.record, 'B')
        }
        save.props.onClick()
        await flush()
        assert.deepEqual(fixture.saves[0], ['fr', [{ language: 'fr', resource: 'product', name: 'A', field: 'image', value: '/files/A.png' }]])
      }
    } finally { fixture.unmount() }
  })
}
