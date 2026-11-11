import { computed, effectScope, reactive, ref, watch } from 'vue'
import { refDebounced } from '@vueuse/core'
import { createAdminCaller } from './adminCaller'
import { storefrontLanguages } from './boot'
import { useAdminAction, useAdminRead } from './api'
import { isStaleWrite } from './errors'
import { __ } from './translation'
import { rememberPreviewEntry, rememberedPreviewEntry } from '../ia/previewEntry'
import { capturePage } from '../utils/capturePage'
import { createSequence } from '../utils/sequence'
import { readableName } from '../utils/sectionSettingToField'

// Section text in the default language is the source the other languages translate.
const sourceLanguage = () => storefrontLanguages[0]?.code ?? 'en'
const DEFAULT_MAX_BLOCKS = 50
const DEFAULT_MAX_PRODUCTS = 8
const SEARCH_DEBOUNCE_MS = 300
const TRANSLATABLE_TYPES = ['text', 'textarea']

const layoutCaller = createAdminCaller('theme_layout.')
const themeCaller = createAdminCaller('theme.')

const thumbnailAction = effectScope(true).run(() => useAdminAction('theme_layout.save_thumbnail', { quiet: true }))

const THUMBNAIL_SIZE = { width: 1280, height: 720, scale: 2, outputWidth: 480, quality: 0.85 }

async function captureThumbnail(theme, scheme) {
  const params = new URLSearchParams({ theme, page: 'index', lang: sourceLanguage() })
  let followsSystem = false
  const image = await capturePage(`/theme_editor_preview?${params}`, {
    ...THUMBNAIL_SIZE,
    beforeCapture: (frameDocument) => {
      const root = frameDocument.documentElement
      followsSystem = root.dataset.colorScheme === 'System'
      if (followsSystem) root.dataset.theme = scheme
      for (const element of frameDocument.querySelectorAll('.wow')) {
        element.classList.remove('wow')
        element.style.visibility = 'visible'
        element.style.animation = 'none'
      }
    },
  })
  return { image, followsSystem }
}

export async function saveThemeThumbnail(theme) {
  const light = await captureThumbnail(theme, 'light')
  await thumbnailAction.submit({ theme, image: light.image, scheme: 'light' })
  const dark = light.followsSystem ? await captureThumbnail(theme, 'dark') : light
  await thumbnailAction.submit({ theme, image: dark.image, scheme: 'dark' })
}

const clone = (value) => JSON.parse(JSON.stringify(value))

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort()
    return `{${keys.map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value ?? null)
}

function uniqueId(base, entries) {
  const taken = new Set(entries.map((entry) => entry.id))
  let number = 1
  while (taken.has(`${base}-${number}`)) number += 1
  return `${base}-${number}`
}

export function isTranslatable(setting) {
  return TRANSLATABLE_TYPES.includes(setting.type)
}

function typedValue(setting, value) {
  if (setting.type !== 'number') return value
  return value === '' || value === null || value === undefined ? null : Number(value)
}

export function maxBlocks(schema) {
  return Number(schema?.max_blocks) || DEFAULT_MAX_BLOCKS
}

export function maxProducts(schema) {
  return Number(schema?.max_products) || DEFAULT_MAX_PRODUCTS
}

export function canAddBlocks(schema) {
  return Object.keys(schema?.blocks ?? {}).length > 0
}

export const SECTION_GROUPS = ['header_group', 'footer_group']

const GROUP_LABELS = { header_group: __('Header group'), footer_group: __('Footer group') }

export function pageLabel(page) {
  if (GROUP_LABELS[page]) return GROUP_LABELS[page]
  if (page === 'index') return __('Home page')
  return readableName(page)
}

const PART_ORDER = ['header_group', null, 'footer_group']

export function acceptsSection(schema, group) {
  const allowed = schema.groups ?? ['pages']
  return allowed.includes(SECTION_GROUPS.includes(group) ? group : 'pages')
}

function createPart(group, data) {
  const layout = clone(data.draft_layout ?? { sections: [] })
  if (!Array.isArray(layout.sections)) layout.sections = []
  return {
    group,
    layout,
    savedLayout: stableJson(data.draft_layout),
    liveLayout: stableJson(data.published_layout ?? data.default_layout),
    // Sent back with each save, so the server refuses one over a change this editor never loaded.
    revision: data.revision,
  }
}

const isUnsaved = (part) => stableJson(part.layout) !== part.savedLayout
const isUnpublished = (part) => stableJson(part.layout) !== part.liveLayout

export function createLayoutEditor(theme) {
  const state = reactive({
    theme,
    page: 'index',
    pages: [],
    hasPreviewEntries: false,
    previewEntry: null,
    schemas: [],
    settings: { doctype: null, groups: [] },
    live: false,
    parts: [],
    language: sourceLanguage(),
    device: 'desktop',
    selection: null,
    previewToken: 0,
    settingsRevision: 0,
    scrollRequest: 0,
    loaded: false,
    loadError: null,
  })

  const schemaByType = computed(() => Object.fromEntries(state.schemas.map((schema) => [schema.type, schema])))

  const hasUnsavedChanges = computed(() => state.parts.some(isUnsaved))
  const hasUnpublishedChanges = computed(() => state.parts.some(isUnpublished))

  const busy = computed(() => layoutCaller.loading.value || themeCaller.loading.value)

  const pagePart = computed(() => state.parts.find((part) => part.group === state.page) ?? null)

  function findPart(group) {
    return (
      state.parts.find((part) => part.group === group) ??
      (SECTION_GROUPS.includes(group) ? null : pagePart.value)
    )
  }

  function findSection(group, sectionId) {
    return findPart(group)?.layout.sections.find((section) => section.id === sectionId) ?? null
  }

  function findBlock(group, sectionId, blockId) {
    return findSection(group, sectionId)?.blocks?.find((block) => block.id === blockId) ?? null
  }

  const selected = computed(() => {
    const selection = state.selection
    if (!selection) return null
    const section = findSection(selection.group, selection.section)
    const sectionSchema = schemaByType.value[section?.type]
    if (!section || !sectionSchema) return null
    const base = { group: selection.group, section, sectionSchema }
    if (selection.kind === 'section') return { ...base, kind: 'section', schema: sectionSchema, owner: section }

    const block = findBlock(selection.group, selection.section, selection.block)
    const schema = sectionSchema.blocks?.[block?.type]
    if (!block || !schema) return null
    return { ...base, kind: 'block', block, schema, owner: block }
  })

  function commit() {
    state.previewToken += 1
  }

  function select(selection, { scroll = true } = {}) {
    state.selection = selection
    if (scroll && selection) state.scrollRequest += 1
  }

  function selectFromPreview({ group, section, id }) {
    if (!id) return
    const part = findPart(group)
    if (!part) return
    const options = { scroll: false }
    if (!section || section === id) {
      if (findSection(part.group, id)) select({ kind: 'section', group: part.group, section: id }, options)
    } else if (findBlock(part.group, section, id)) {
      select({ kind: 'block', group: part.group, section, block: id }, options)
    } else if (findSection(part.group, section)) {
      select({ kind: 'section', group: part.group, section }, options)
    }
  }

  function adoptPart(data) {
    const part = createPart(data.page, data)
    const index = state.parts.findIndex((existing) => existing.group === part.group)
    if (index === -1) state.parts.push(part)
    else state.parts.splice(index, 1, part)
  }

  function forgetLostSelection() {
    if (state.selection && !selected.value) state.selection = null
  }

  // Two quick page picks each load; get_editor is one shared request, so the second aborts the
  // first, and the first's loop over the header and footer would abort the second in turn. Only
  // the newest load may write the editor's state.
  const loads = createSequence()
  let settingsAdopted = false

  async function load(page = state.page) {
    const ticket = loads.next()
    const { data, error } = await layoutCaller.attempt('get_editor', { theme, page })
    if (!loads.isLatest(ticket)) return false
    state.loadError = error
    if (data) {
      const groups = SECTION_GROUPS.filter((group) => data.pages.includes(group) && group !== page)
      const groupData = []
      for (const group of groups) {
        groupData.push(await layoutCaller.call('get_editor', { theme, page: group }))
        if (!loads.isLatest(ticket)) return false
      }
      state.page = data.page
      state.pages = data.pages
      state.hasPreviewEntries = data.has_preview_entries
      state.previewEntry = data.has_preview_entries ? rememberedPreviewEntry(theme, data.page) : null
      state.schemas = data.section_schemas
      // Theme settings belong to the theme, not the page, and saveThemeSettings() keeps this copy
      // current. Re-adopting them on a page switch would wipe what is typed in the open panel.
      if (!settingsAdopted) {
        state.settings = data.settings
        settingsAdopted = true
      }
      state.live = data.live
      state.parts = []
      for (const partData of [data, ...groupData.filter(Boolean)]) adoptPart(partData)
      state.parts.sort(
        (first, second) =>
          PART_ORDER.indexOf(SECTION_GROUPS.includes(first.group) ? first.group : null) -
          PART_ORDER.indexOf(SECTION_GROUPS.includes(second.group) ? second.group : null),
      )
      forgetLostSelection()
    }
    state.loaded = true
    commit()
    return Boolean(data)
  }

  async function runOnParts(method, parts, withLayout = true) {
    for (const part of parts) {
      const params = { theme, page: part.group }
      if (withLayout) Object.assign(params, { layout: clone(part.layout), revision: part.revision })
      const { data, error } = await layoutCaller.attempt(method, params)
      if (!data) {
        // The wrapper already toasted why. A stale page reloads, since saving it again would fail
        // the same way; otherwise parts before this one have landed and the preview must show them.
        if (isStaleWrite(error)) await load(state.page)
        else commit()
        return false
      }
      const layout = part.layout
      adoptPart(data)
      if (method !== 'discard') findPart(part.group).layout = layout
    }
    forgetLostSelection()
    commit()
    return true
  }

  const save = () => runOnParts('save_draft', state.parts.filter(isUnsaved))
  async function publish() {
    if (!(await saveIfChanged())) return false
    return runOnParts('publish', state.parts.filter(isUnpublished))
  }
  const discard = () => runOnParts('discard', [...state.parts], false)

  async function saveIfChanged() {
    return hasUnsavedChanges.value ? save() : true
  }

  function setPreviewEntry(entry) {
    state.previewEntry = entry
    rememberPreviewEntry(theme, state.page, entry)
    commit()
  }

  async function switchPage(page) {
    if (page === state.page || !(await saveIfChanged())) return
    state.selection = null
    await load(page)
  }

  function sectionIndexBelowSelection(part) {
    const sectionId = state.selection?.group === part.group ? state.selection.section : null
    const index = part.layout.sections.findIndex((section) => section.id === sectionId)
    return index === -1 ? part.layout.sections.length : index + 1
  }

  function addSection(group, type) {
    const part = findPart(group)
    if (!part) return
    const section = {
      id: uniqueId(type, part.layout.sections),
      type,
      hidden: false,
      settings: {},
      blocks: [],
    }
    part.layout.sections.splice(sectionIndexBelowSelection(part), 0, section)
    select({ kind: 'section', group: part.group, section: section.id })
    commit()
  }

  function addBlock(group, sectionId, type) {
    const section = findSection(group, sectionId)
    if (!section || (section.blocks ?? []).length >= maxBlocks(schemaByType.value[section.type])) return
    section.blocks ??= []
    const block = { id: uniqueId(type, section.blocks), type, settings: {} }
    section.blocks.push(block)
    select({ kind: 'block', group, section: section.id, block: block.id })
    commit()
  }

  function duplicateSection(group, sectionId) {
    const sections = findPart(group)?.layout.sections ?? []
    const index = sections.findIndex((section) => section.id === sectionId)
    if (index === -1) return
    const copy = clone(sections[index])
    copy.id = uniqueId(copy.type, sections)
    sections.splice(index + 1, 0, copy)
    select({ kind: 'section', group, section: copy.id })
    commit()
  }

  function duplicateBlock(group, sectionId, blockId) {
    const section = findSection(group, sectionId)
    const index = section?.blocks?.findIndex((block) => block.id === blockId) ?? -1
    if (index === -1 || section.blocks.length >= maxBlocks(schemaByType.value[section.type])) return
    const copy = clone(section.blocks[index])
    copy.id = uniqueId(copy.type, section.blocks)
    section.blocks.splice(index + 1, 0, copy)
    select({ kind: 'block', group, section: sectionId, block: copy.id })
    commit()
  }

  function removeSection(group, sectionId) {
    const sections = findPart(group)?.layout.sections ?? []
    const index = sections.findIndex((section) => section.id === sectionId)
    if (index === -1) return
    sections.splice(index, 1)
    if (state.selection?.group === group && state.selection.section === sectionId) state.selection = null
    commit()
  }

  function removeBlock(group, sectionId, blockId) {
    const section = findSection(group, sectionId)
    const index = section?.blocks?.findIndex((block) => block.id === blockId) ?? -1
    if (index === -1) return
    section.blocks.splice(index, 1)
    const selection = state.selection
    if (selection?.group === group && selection.section === sectionId && selection.block === blockId) {
      state.selection = { kind: 'section', group, section: sectionId }
    }
    commit()
  }

  function toggleHidden(group, sectionId) {
    const section = findSection(group, sectionId)
    if (!section) return
    section.hidden = !section.hidden
    commit()
  }

  function moveEntry(list, entryId, newIndex) {
    const index = list.findIndex((entry) => entry.id === entryId)
    if (index === -1 || index === newIndex) return
    const [entry] = list.splice(index, 1)
    list.splice(newIndex, 0, entry)
    commit()
  }

  const moveSection = (group, sectionId, newIndex) =>
    moveEntry(findPart(group)?.layout.sections ?? [], sectionId, newIndex)
  const moveBlock = (group, sectionId, blockId, newIndex) =>
    moveEntry(findSection(group, sectionId)?.blocks ?? [], blockId, newIndex)

  function settingValue(owner, setting) {
    const value = owner.settings?.[setting.id] ?? setting.default
    if (!isTranslatable(setting)) return value
    if (value && typeof value === 'object') {
      return value[state.language] ?? (state.language === sourceLanguage() ? value.en : null) ?? ''
    }
    return state.language === sourceLanguage() ? (value ?? '') : ''
  }

  function settingPlaceholder(owner, setting) {
    if (!isTranslatable(setting) || state.language === sourceLanguage()) return ''
    const value = owner.settings?.[setting.id] ?? setting.default
    return (value && typeof value === 'object' ? (value[sourceLanguage()] ?? value.en) : value) ?? ''
  }

  function translatedValue(current, value) {
    if (state.language === sourceLanguage()) {
      return current && typeof current === 'object' ? { ...current, [sourceLanguage()]: value } : value
    }

    const translations = current && typeof current === 'object' ? { ...current } : current ? { [sourceLanguage()]: current } : {}
    if (value === '' || value === null) delete translations[state.language]
    else translations[state.language] = value
    return translations
  }

  function setSetting(owner, setting, value) {
    owner.settings ??= {}
    owner.settings[setting.id] = isTranslatable(setting)
      ? translatedValue(owner.settings[setting.id] ?? setting.default, value)
      : typedValue(setting, value)
  }

  async function saveThemeSettings(changes) {
    const data = await themeCaller.call('save_theme_settings', { theme: state.theme, ...changes })
    if (!data) return false
    for (const field of state.settings.groups.flatMap((group) => group.fields)) {
      if (field.fieldname in changes) field.value = changes[field.fieldname]
    }
    state.settingsRevision += 1
    commit()
    return true
  }

  return {
    state,
    schemaByType,
    pagePart,
    selected,
    hasUnsavedChanges,
    hasUnpublishedChanges,
    busy,
    load,
    save,
    publish,
    discard,
    saveIfChanged,
    switchPage,
    setPreviewEntry,
    select,
    selectFromPreview,
    addSection,
    addBlock,
    duplicateSection,
    duplicateBlock,
    removeSection,
    removeBlock,
    toggleHidden,
    moveSection,
    moveBlock,
    settingValue,
    settingPlaceholder,
    setSetting,
    saveThemeSettings,
    commit,
  }
}

export function usePreviewEntries(state) {
  const query = ref('')
  const search = refDebounced(query, SEARCH_DEBOUNCE_MS)
  const start = ref(0)
  const entries = ref([])

  const results = useAdminRead('theme_layout.get_preview_entries', {
    params: () => ({
      theme: state.theme,
      page: state.page,
      search: search.value,
      start: start.value,
      selected: state.previewEntry,
    }),
    refetch: true,
  })

  watch([search, () => state.page, () => state.previewEntry], () => (start.value = 0))
  watch(
    () => results.data,
    (data) => {
      if (!data) return
      entries.value = start.value ? [...entries.value, ...data.entries] : data.entries
    },
  )

  const current = computed(() => results.data?.current ?? null)
  const hasMore = computed(() => Boolean(results.data?.has_more))
  const showMore = () => (start.value = entries.value.length)

  return { query, results, entries, current, hasMore, showMore }
}
