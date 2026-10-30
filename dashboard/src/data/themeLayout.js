import { computed, reactive } from 'vue'
import { createAdminCaller } from './adminCaller'

const DEFAULT_MAX_BLOCKS = 50
const DEFAULT_MAX_PRODUCTS = 8
const TRANSLATABLE_TYPES = ['text', 'textarea']

const layoutCaller = createAdminCaller('theme_layout.')
const themeCaller = createAdminCaller('theme.')

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
    liveLayout: stableJson(data.published_layout ?? data.theme_file_layout),
  }
}

const isUnsaved = (part) => stableJson(part.layout) !== part.savedLayout
const isUnpublished = (part) => stableJson(part.layout) !== part.liveLayout

export function createLayoutEditor(theme) {
  const state = reactive({
    theme,
    page: 'index',
    pages: [],
    schemas: [],
    settings: { doctype: null, groups: [] },
    live: false,
    parts: [],
    language: 'en',
    device: 'desktop',
    selection: null,
    previewToken: 0,
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
    if (selection.kind === 'theme') return { kind: 'theme' }

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
    if (state.selection && state.selection.kind !== 'theme' && !selected.value) state.selection = null
  }

  async function load(page = state.page) {
    const { data, error } = await layoutCaller.attempt('get_editor', { theme, page })
    state.loadError = error
    if (data) {
      state.page = data.page
      state.pages = data.pages
      state.schemas = data.section_schemas
      state.settings = data.settings
      state.live = data.live
      const groups = SECTION_GROUPS.filter((group) => data.pages.includes(group) && group !== page)
      const groupData = await Promise.all(
        groups.map((group) => layoutCaller.call('get_editor', { theme, page: group })),
      )
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
      if (withLayout) params.layout = clone(part.layout)
      const data = await layoutCaller.call(method, params)
      if (!data) return false
      const layout = part.layout
      adoptPart(data)
      if (method !== 'discard') findPart(part.group).layout = layout
    }
    forgetLostSelection()
    commit()
    return true
  }

  const save = () => runOnParts('save_draft', state.parts.filter(isUnsaved))
  const publish = () =>
    runOnParts('publish', state.parts.filter((part) => isUnsaved(part) || isUnpublished(part)))
  const discard = () => runOnParts('discard', [...state.parts], false)

  async function saveIfChanged() {
    return hasUnsavedChanges.value ? save() : true
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
    if (value && typeof value === 'object') return value[state.language] ?? ''
    return state.language === 'en' ? (value ?? '') : ''
  }

  function settingPlaceholder(owner, setting) {
    if (!isTranslatable(setting) || state.language === 'en') return ''
    const value = owner.settings?.[setting.id] ?? setting.default
    return (value && typeof value === 'object' ? value.en : value) ?? ''
  }

  function translatedValue(current, value) {
    if (state.language === 'en') {
      return current && typeof current === 'object' ? { ...current, en: value } : value
    }

    const translations = current && typeof current === 'object' ? { ...current } : current ? { en: current } : {}
    if (value === '' || value === null) delete translations[state.language]
    else translations[state.language] = value
    return translations
  }

  function setSetting(owner, setting, value) {
    owner.settings ??= {}
    owner.settings[setting.id] = isTranslatable(setting)
      ? translatedValue(owner.settings[setting.id], value)
      : value
  }

  async function saveThemeSetting(field, value) {
    if (value === (field.value ?? '')) return false
    const data = await themeCaller.call('save_theme_settings', { [field.fieldname]: value })
    if (!data) return false
    field.value = value
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
    saveThemeSetting,
    commit,
  }
}
