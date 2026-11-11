import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import { uploadTranslationImage } from '../../src/data/translationImage.js'
import { changePending } from '../../src/data/translationEditorState.js'
import { fieldKey } from '../../src/data/translationStatus.js'

test('a deferred image upload retains its original record and field after navigation', async () => {
  let resolve
  const response = new Promise((done) => { resolve = done })
  const pending = {}
  let record = 'A'
  const field = { field: 'image', value: '', status: 'missing' }
  const key = fieldKey('fr', 'product', record, field.field)
  const uploading = uploadTranslationImage(() => response, {}, key, field,
    (identity, original, value) => changePending(pending, identity, original, value))
  record = 'B'
  field.value = '/files/A.png'
  resolve({ file_url: '/files/A.png' })
  await uploading
  assert.deepEqual(pending, { [key]: '/files/A.png' })
  assert.equal(pending[fieldKey('fr', 'product', record, field.field)], undefined)
})

test('the field emits the upload identity captured before its props change', async () => {
  const source = readFileSync(new URL('../../src/components/translations/TranslationField.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'translation-field-test' }).content
    .replace(/^import .*$/gm, '').replace('export default', 'return')
  const stubs = 'const Button = {}, FormControl = {}, Editor = {}, EditorContent = {}, RichTextKit = {}, RichTextField = {}, StatusBadge = {}, Thumb = {};'
  let resolve
  const response = new Promise((done) => { resolve = done })
  const component = new Function('computed', 'ref', 'useFileUpload', 'uploadTranslationImage', 'toast', '__', stubs + script)(
    computed, ref, () => ({ upload: () => response }), uploadTranslationImage,
    { error: assert.fail }, (text) => text,
  )
  const key = fieldKey('fr', 'product', 'A', 'image')
  const field = { field: 'image', value: '', status: 'missing' }
  const props = { identity: key, field, disabled: false }
  const pending = {}
  const state = component.setup(props, {
    expose() {},
    emit(event, value, identity, original) {
      assert.equal(event, 'change')
      changePending(pending, identity, original, value)
    },
  })
  const uploading = state.swapImage({ target: { files: [{ name: 'A.png' }], value: 'A.png' } })
  props.identity = fieldKey('de', 'collection', 'B', 'banner')
  props.field = { field: 'banner', value: '/files/B.png', status: 'current' }
  resolve({ file_url: '/files/A.png' })
  await uploading
  assert.deepEqual(pending, { [key]: '/files/A.png' })
  assert.equal(state.isUploading.value, false)
})
