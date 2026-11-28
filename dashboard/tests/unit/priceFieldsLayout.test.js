import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Vue from 'vue'
import { findNode, loadComponent, mount, shell } from '../helpers/mountVue.js'
import { hasPrice } from '../../src/data/product.js'

const field = {
  props: ['label', 'error'],
  render() { return Vue.h('field', { label: this.label }, [this.$slots.prefix?.(), Vue.h('input'), this.$slots.suffix?.()]) },
}
const PriceFields = loadComponent('components/PriceFields', {
  Button: shell, FormControl: field, hasPrice, symbolFor: () => '₹', __: (text) => text,
})

function render(originalPrice) {
  const model = Vue.reactive({ price: 499, originalPrice })
  const { root } = mount({
    render: () => Vue.h(PriceFields, {
      price: model.price,
      originalPrice: model.originalPrice,
      'onUpdate:originalPrice': (value) => { model.originalPrice = value },
    }),
  })
  const find = (predicate) => findNode(root, predicate)
  return {
    model,
    original: () => find((node) => node.props.label === 'Original price'),
    button: (label) => find((node) => node.type === 'button' && (node.props['aria-label'] ?? node.children[0]?.text) === label),
    isTwoColumns: () => find((node) => node.props.class?.includes('grid-cols-1')).props.class.includes('sm:grid-cols-2'),
  }
}

test('Price stands alone at full width with the add link until an original price is added', async () => {
  const view = render(null)
  assert.equal(view.original(), undefined)
  assert.equal(view.isTwoColumns(), false)

  await view.button('Add original price').props.onClick()
  assert.ok(view.original())
  assert.equal(view.isTwoColumns(), true)
  assert.equal(view.button('Add original price'), undefined)
})

test('a stored original price shows, and × clears and hides it', async () => {
  const view = render(899)
  assert.ok(view.original())

  view.button('Remove original price').props.onClick()
  await Vue.nextTick()
  assert.equal(view.model.originalPrice, null)
  assert.equal(view.original(), undefined)
  assert.ok(view.button('Add original price'))
})

test('adding an original price moves focus into the new field, since the add button unmounts', async () => {
  const view = render(null)
  await view.button('Add original price').props.onClick()
  assert.equal(view.original().children.find((node) => node.type === 'input').focused, true)
})
