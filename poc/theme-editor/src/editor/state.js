import { computed, reactive, watch } from 'vue'
import { createBlock, createSection, defaultTheme, newId } from '../theme/layouts.js'
import { SECTIONS, schemaFor } from '../theme/schemas.js'
import { BUILDER_PAGES } from '../theme/builder.js'

// Stands in for the site database. In Commera a Theme Layout record per
// (theme, template) holds `layout` (draft) and `published_layout`; the theme's
// files are never written. localStorage plays that role here.
const storage = {
  read(key) {
    try {
      return JSON.parse(localStorage.getItem(key))
    } catch {
      return null
    }
  },
  write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* private mode: the prototype still works, it just forgets on reload */
    }
  },
}

const clone = (value) => JSON.parse(JSON.stringify(value))

export function createEditor(themeName) {
  const draftKey = `commera:theme-layout:${themeName}:draft`
  const publishedKey = `commera:theme-layout:${themeName}:published`
  const published = storage.read(publishedKey) ?? defaultTheme()

  const state = reactive({
    theme: themeName,
    draft: storage.read(draftKey) ?? clone(published),
    savedDraft: null,
    published,
    template: 'index',
    language: 'en',
    device: 'desktop',
    selectedId: null,
    // Bumped when the editor (not the preview) changes the selection, so the
    // preview scrolls to it; a click inside the preview must not scroll.
    scrollRequest: 0,
  })
  state.savedDraft = JSON.stringify(state.draft)

  const hasUnsavedChanges = computed(() => JSON.stringify(state.draft) !== state.savedDraft)
  const hasUnpublishedChanges = computed(() => JSON.stringify(state.draft) !== JSON.stringify(state.published))

  // A page is either a theme template ('index', 'product', …) or a Builder
  // page ('builder:<name>'), whose content lives in Builder, not in a layout.
  const builderPage = computed(() =>
    state.template.startsWith('builder:') ? BUILDER_PAGES.find((page) => `builder:${page.name}` === state.template) : null,
  )

  // Every section on the current page, in render order, tagged with its place.
  // A Builder page has no template sections here; it keeps the theme's header
  // and footer only when it uses the store layout.
  const places = computed(() => {
    if (builderPage.value) {
      if (builderPage.value.layout !== 'commera-theme') return []
      return [
        { place: 'header', label: 'Header', sections: state.draft.groups.header },
        { place: 'footer', label: 'Footer', sections: state.draft.groups.footer },
      ]
    }
    return [
      { place: 'header', label: 'Header', sections: state.draft.groups.header },
      { place: 'template', label: 'Template', sections: state.draft.templates[state.template] },
      { place: 'footer', label: 'Footer', sections: state.draft.groups.footer },
    ]
  })

  function locate(id) {
    for (const { place, sections } of places.value) {
      const sectionIndex = sections.findIndex((section) => section.id === id)
      if (sectionIndex !== -1) {
        const section = sections[sectionIndex]
        return { kind: 'section', place, list: sections, index: sectionIndex, node: section, section }
      }
      for (const section of sections) {
        const blockIndex = section.blocks.findIndex((block) => block.id === id)
        if (blockIndex !== -1) {
          return { kind: 'block', place, list: section.blocks, index: blockIndex, node: section.blocks[blockIndex], section }
        }
      }
    }
    return null
  }

  const selection = computed(() => {
    if (state.selectedId === 'theme-settings') return { kind: 'theme', node: { settings: state.draft.settings } }
    if (state.selectedId === 'builder-page') return builderPage.value ? { kind: 'builder-page', node: builderPage.value } : null
    return state.selectedId ? locate(state.selectedId) : null
  })

  const selectedSchema = computed(() => {
    const found = selection.value
    if (!found) return null
    return schemaFor({ kind: found.kind, type: found.node.type, sectionType: found.section?.type })
  })

  function select(id, { scroll = true } = {}) {
    state.selectedId = id
    if (scroll) state.scrollRequest++
  }

  function addSection(place, type) {
    const section = createSection(type)
    const list = place === 'template' ? state.draft.templates[state.template] : state.draft.groups[place]
    // New sections land before a group's static section (the header stays
    // last in the header group, the footer stays last in the footer group).
    const staticIndex = list.findIndex((existing) => SECTIONS[existing.type].static)
    list.splice(place !== 'template' && staticIndex !== -1 ? staticIndex : list.length, 0, section)
    select(section.id)
  }

  function addBlock(sectionId, blockType) {
    const found = locate(sectionId)
    const block = createBlock(found.section.type, blockType)
    found.section.blocks.push(block)
    select(block.id)
  }

  function remove(id) {
    const found = locate(id)
    if (!found) return
    found.list.splice(found.index, 1)
    if (state.selectedId === id) state.selectedId = found.kind === 'block' ? found.section.id : null
  }

  function duplicate(id) {
    const found = locate(id)
    const copy = clone(found.node)
    copy.id = newId(copy.type.split('/').pop())
    copy.blocks?.forEach((block) => (block.id = newId(block.type.split('/').pop())))
    found.list.splice(found.index + 1, 0, copy)
    select(copy.id)
  }

  function toggleHidden(id) {
    const found = locate(id)
    found.node.disabled = !found.node.disabled
  }

  // Applies a committed Tree drag. The Tree's `move` rule already limits drops
  // to siblings of the same kind under the same parent.
  function move(id, newIndex) {
    const found = locate(id)
    if (!found) return
    const [node] = found.list.splice(found.index, 1)
    found.list.splice(newIndex, 0, node)
  }

  function setValue(settingId, value, translatable) {
    const settings = selection.value.node.settings
    if (translatable) {
      settings[settingId] = { ...(settings[settingId] ?? {}), [state.language]: value }
    } else {
      settings[settingId] = value
    }
  }

  function saveDraft() {
    storage.write(draftKey, state.draft)
    state.savedDraft = JSON.stringify(state.draft)
  }

  function publish() {
    saveDraft()
    state.published = clone(state.draft)
    storage.write(publishedKey, state.published)
  }

  function discardDraft() {
    state.draft = clone(state.published)
    saveDraft()
    state.selectedId = null
  }

  // The preview only needs what it renders: the page's sections and theme settings.
  const previewPayload = computed(() => ({
    settings: clone(state.draft.settings),
    header: builderPage.value && builderPage.value.layout !== 'commera-theme' ? [] : clone(state.draft.groups.header),
    template: state.template,
    sections: builderPage.value ? [] : clone(state.draft.templates[state.template]),
    builderPage: builderPage.value ? clone(builderPage.value) : null,
    footer: builderPage.value && builderPage.value.layout !== 'commera-theme' ? [] : clone(state.draft.groups.footer),
    language: state.language,
    selectedId: state.selectedId,
  }))

  // Leaving a page for another deselects: the selection belongs to the page.
  watch(
    () => state.template,
    () => {
      if (builderPage.value) {
        state.selectedId = 'builder-page'
      } else if (state.selectedId && state.selectedId !== 'theme-settings' && !locate(state.selectedId)) {
        state.selectedId = null
      }
    },
  )

  return {
    state,
    builderPage,
    places,
    selection,
    selectedSchema,
    hasUnsavedChanges,
    hasUnpublishedChanges,
    previewPayload,
    locate,
    select,
    addSection,
    addBlock,
    remove,
    duplicate,
    toggleHidden,
    move,
    setValue,
    saveDraft,
    publish,
    discardDraft,
  }
}
