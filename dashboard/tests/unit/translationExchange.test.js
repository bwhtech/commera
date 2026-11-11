import assert from 'node:assert/strict'
import { test } from 'node:test'
import { exportTranslationsUrl, translatableLanguages } from '../../src/data/translationExchange.js'

test('the export link names the admin method and the language', () => {
  assert.equal(
    exportTranslationsUrl('pt-BR'),
    '/api/method/commera.api.admin.translations.export_translations?language=pt-BR',
  )
})

test('every storefront language but the default can be translated', () => {
  const languages = [{ code: 'en' }, { code: 'ar' }, { code: 'fr' }]
  assert.deepEqual(translatableLanguages(languages).map(({ code }) => code), ['ar', 'fr'])
  assert.deepEqual(translatableLanguages([]), [])
})

test('mounted CSV controls reconcile the first target, default changes, and removal', async () => {
  const { effectScope } = await import('vue')
  const { setStorefrontLanguages } = await import('../../src/data/boot.js')
  const { useTranslationLanguages } = await import('../../src/data/translationExchange.js')
  const scope = effectScope()
  try {
    setStorefrontLanguages([{ code: 'en', name: 'English' }])
    const controls = scope.run(() => useTranslationLanguages())
    assert.equal(controls.language.value, '')
    setStorefrontLanguages([{ code: 'en', name: 'English' }, { code: 'ar', name: 'Arabic' }])
    assert.equal(controls.language.value, 'ar')
    assert.deepEqual(controls.languageOptions.value, [{ label: 'Arabic', value: 'ar' }])
    setStorefrontLanguages([{ code: 'ar', name: 'Arabic' }, { code: 'en', name: 'English' }])
    assert.equal(controls.language.value, 'en')
    assert.deepEqual(controls.languageOptions.value, [{ label: 'English', value: 'en' }])
    setStorefrontLanguages([{ code: 'ar', name: 'Arabic' }])
    assert.equal(controls.language.value, '')
  } finally {
    scope.stop()
    setStorefrontLanguages([])
  }
})
