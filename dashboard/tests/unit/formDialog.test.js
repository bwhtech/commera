import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { findNode, loadComponent, mount, shell } from '../helpers/mountVue.js'

const primitive = (tag) => ({ render() { return Vue.h(tag, this.$attrs, this.$slots.default?.()) } })
// Dialog and BottomSheet stand in as tagged boxes, so a test can tell which one the shell drew.
const surface = (tag) => ({
  props: ['open', 'dismissible'],
  render() { return Vue.h(tag, { dismissible: this.dismissible }, this.$slots.default?.()) },
})

function loadFormDialog({ isMobile = false, confirmLeave = async () => true } = {}) {
  const viewport = Vue.ref(isMobile)
  const DialogShell = loadComponent('components/DialogShell', {
    BottomSheet: surface('bottom-sheet'), Button: shell, Dialog: surface('dialog'),
    DialogTitle: primitive('dialog-title'), useIsMobile: () => viewport,
    // No content element in the test renderer, so the shell's attribute fixes have nothing to touch.
    injectDialogRootContext: () => ({ descriptionId: '', contentElement: Vue.ref(null) }),
    useDialogLayer: () => Vue.ref(false),
  })
  return loadComponent('components/FormDialog', {
    Button: shell, DialogDescription: primitive('dialog-description'), DialogShell,
    __: (text) => text, confirmLeave, useIsMobile: () => viewport,
  })
}

function render(props, options) {
  const FormDialog = loadFormDialog(options)
  const state = Vue.reactive({ open: true })
  const { root } = mount({
    render: () => Vue.h(FormDialog, {
      open: state.open, 'onUpdate:open': (value) => (state.open = value), primaryLabel: 'Save', ...props,
    }),
  })
  const textOf = (node) => node.text + node.children.map(textOf).join('')
  const all = (type, node = root) => [...(node.type === type ? [node] : []), ...node.children.flatMap((child) => all(type, child))]
  const button = (label) => findNode(root, (node) => node.type === 'button' && textOf(node).trim() === label)
  return { root, state, textOf, all, button }
}

const settle = () => new Promise((resolve) => setTimeout(resolve))

test('the title is the dialog title primitive, so the dialog is named by it', () => {
  const { root, textOf } = render({ title: 'Add product' })
  assert.equal(textOf(findNode(root, (node) => node.type === 'dialog-title')), 'Add product')
})

test('a description renders once in the header, as the dialog description', () => {
  const { textOf, all } = render({ title: 'Black', description: 'Color of Cotton tee', note: 'Photos save as you add them.' })
  const descriptions = all('dialog-description')
  assert.equal(descriptions.length, 1)
  assert.equal(textOf(descriptions[0]).trim(), 'Color of Cotton tee')
})

test('without a description the footer line describes the dialog, and stays in place when empty', () => {
  const { textOf, all } = render({ title: 'Add stock', reason: 'Enter a quantity to add.' })
  assert.equal(textOf(all('dialog-description')[0]).trim(), 'Enter a quantity to add.')
  assert.equal(render({ title: 'Add stock' }).all('dialog-description').length, 1)
})

test('below sm the same dialog is a bottom sheet', () => {
  assert.equal(render({ title: 'Add stock' }, { isMobile: true }).all('bottom-sheet').length, 1)
  assert.equal(render({ title: 'Add stock' }).all('bottom-sheet').length, 0)
})

test('a clean dialog closes on Cancel without asking', async () => {
  let asked = 0
  const { state, button } = render({ title: 'Add product' }, { confirmLeave: async () => (asked += 1, true) })
  button('Cancel').props.onClick()
  await settle()
  assert.equal(asked, 0)
  assert.equal(state.open, false)
})

test('a dirty dialog asks first, and stays open when the merchant keeps editing', async () => {
  const { state, button } = render({ title: 'Add product', dirty: true }, { confirmLeave: async () => false })
  button('Cancel').props.onClick()
  await settle()
  assert.equal(state.open, true)
})

test('a dirty dialog closes once the merchant discards', async () => {
  const { state, button } = render({ title: 'Add product', dirty: true }, { confirmLeave: async () => true })
  button('Cancel').props.onClick()
  await settle()
  assert.equal(state.open, false)
})

test('a dirty sheet cannot be swiped or tapped away, because a swipe cannot be asked', () => {
  const sheet = (dirty) => render({ title: 'Add product', dirty }, { isMobile: true }).all('bottom-sheet')[0]
  assert.equal(sheet(true).props.dismissible, false)
  assert.equal(sheet(false).props.dismissible, true)
})

test('a sheet draws its own title, with the × on its row only when asked for', () => {
  const sheet = (closeButton) => {
    const DialogShell = loadComponent('components/DialogShell', {
      BottomSheet: surface('bottom-sheet'), Button: shell, Dialog: surface('dialog'),
      DialogTitle: primitive('dialog-title'), useIsMobile: () => Vue.ref(true),
      injectDialogRootContext: () => ({ descriptionId: '', contentElement: Vue.ref(null) }),
      useDialogLayer: () => Vue.ref(false),
    })
    return mount({ render: () => Vue.h(DialogShell, { open: true, title: 'Import products', closeButton }) }).root
  }
  const withClose = sheet('always')
  const title = findNode(withClose, (node) => node.type === 'dialog-title')
  assert.equal(title.children.map((child) => child.text).join(''), 'Import products')
  assert.ok(title.parent.children.some((node) => node.type === 'button'))
  assert.equal(findNode(sheet('desktop'), (node) => node.type === 'button'), undefined)
})
