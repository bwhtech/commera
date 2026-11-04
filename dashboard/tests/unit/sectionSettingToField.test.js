import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sectionSettingToField } from '../../src/utils/sectionSettingToField.js'

const EXPECTED_FIELDTYPES = {
  text: 'Data',
  textarea: 'Small Text',
  url: 'Data',
  image: 'Attach Image',
  number: 'Float',
  checkbox: 'Check',
  select: 'Select',
  collection: 'Collection',
  products: 'Products',
}

test('every section setting type maps to a field', () => {
  for (const [type, fieldtype] of Object.entries(EXPECTED_FIELDTYPES)) {
    const field = sectionSettingToField({ id: `${type}_setting`, type, label: 'Label', default: 'x' })
    assert.equal(field.fieldtype, fieldtype, type)
    assert.equal(field.fieldname, `${type}_setting`)
    assert.equal(field.label, 'Label')
    assert.equal(field.default, 'x')
  }
})

test('select options become newline separated docfield options', () => {
  const field = sectionSettingToField({ id: 'source', type: 'select', options: ['newest', 'on_sale'] })
  assert.equal(field.options, 'newest\non_sale')
  assert.equal(field.label, 'source')
})

test('select options get readable labels', () => {
  const field = sectionSettingToField({ id: 'source', type: 'select', options: ['hand_picked', 'on_sale', 'main-menu'] })
  assert.deepEqual(field.option_labels, { hand_picked: 'Hand picked', on_sale: 'On sale', 'main-menu': 'Main menu' })
})

test('an unknown type is refused', () => {
  assert.throws(() => sectionSettingToField({ id: 'video', type: 'video' }), /Unknown section setting type/)
})
