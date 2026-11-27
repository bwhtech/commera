import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { findNode, loadComponent, mount, shell } from '../helpers/mountVue.js'

const primitive = (tag) => ({ render() { return Vue.h(tag, this.$attrs, this.$slots.default?.()) } })
const passThrough = { render() { return Vue.h('div', this.$slots.default?.()) } }
const FormDialog = loadComponent('components/FormDialog', {
  Button: shell, Dialog: passThrough, DialogTitle: primitive('dialog-title'), DialogDescription: primitive('dialog-description'),
})

function render(props) {
  const { root } = mount({ render: () => Vue.h(FormDialog, { open: true, primaryLabel: 'Save', ...props }) })
  const textOf = (node) => node.text + node.children.map(textOf).join('')
  const all = (type, node = root) => [...(node.type === type ? [node] : []), ...node.children.flatMap((child) => all(type, child))]
  return { root, textOf, all }
}

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
