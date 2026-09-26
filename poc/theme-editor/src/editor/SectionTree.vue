<script setup>
import { ref, watch } from 'vue'
import { Button, Dropdown, Tree } from 'frappe-ui'
import { APP_BLOCKS, SECTIONS, addableSections } from '../theme/schemas.js'

const props = defineProps({ editor: { type: Object, required: true } })
const { state, places, select, addSection, addBlock, remove, duplicate, toggleHidden, move } = props.editor

const t = (value) => (value && typeof value === 'object' ? value[state.language] || value.en : value)

// A section's row reads better with its own heading ("Best picks") than its
// type name ("Featured products") when a page has two of the same section.
function sectionLabel(section) {
  return SECTIONS[section.type].name
}

function blockLabel(section, block) {
  const app = APP_BLOCKS[block.type]
  if (app) return app.name
  const schema = SECTIONS[section.type].blocks[block.type]
  return schema.name
}

// A row's own heading ("Best picks") tells two sections of the same type apart.
const detailOf = (settings) => t(settings.heading) || t(settings.quote) || ''

// Tree owns per-node `expanded`, but the nodes are rebuilt from the layout on
// every edit; carrying the flags over by key keeps rows open across edits.
const nodes = ref([])

function build() {
  const previous = new Map()
  const collect = (list) => list.forEach((node) => (previous.set(node.key, node.expanded), collect(node.children ?? [])))
  collect(nodes.value)
  const expanded = (key, fallback) => previous.get(key) ?? fallback

  nodes.value = places.value.map(({ place, label, sections }) => ({
    key: `group:${place}`,
    kind: 'group',
    place,
    label,
    expanded: expanded(`group:${place}`, true),
    children: sections.map((section) => ({
      key: section.id,
      kind: 'section',
      place,
      label: sectionLabel(section),
      detail: detailOf(section.settings),
      icon: SECTIONS[section.type].icon,
      hidden: section.disabled,
      static: SECTIONS[section.type].static,
      canAddBlocks: Boolean(SECTIONS[section.type].blocks || SECTIONS[section.type].accepts_apps),
      // A block selected from the preview must be visible in the tree, so its
      // section opens even if the merchant had collapsed it.
      // The page's main section (product information) starts open: its blocks
      // are what merchants come to rearrange on that page.
      expanded:
        section.blocks.some((block) => block.id === state.selectedId) ||
        expanded(section.id, Boolean(SECTIONS[section.type].static && place === 'template')),
      children: section.blocks.map((block) => ({
        key: block.id,
        kind: 'block',
        parent: section.id,
        label: blockLabel(section, block),
        detail: detailOf(block.settings),
        icon: APP_BLOCKS[block.type]?.icon ?? SECTIONS[section.type].blocks[block.type].icon,
        app: APP_BLOCKS[block.type]?.app,
        hidden: block.disabled,
      })),
    })),
  }))
}

watch(() => [state.draft, state.template, state.language, state.selectedId], build, { deep: true, immediate: true })

// Sections reorder within their own group, blocks within their own section;
// nothing is re-parented, since a block only exists inside its section type.
function allowMove({ node, target, position }) {
  if (node.kind === 'group' || position === 'inside' || node.kind !== target.kind) return false
  return node.kind === 'section' ? node.place === target.place : node.parent === target.parent
}

function onDragEnd(info) {
  if (info) move(info.node.key, info.newIndex)
}

function sectionMenu(place) {
  return addableSections(place, state.template).map((section) => ({
    label: section.name,
    icon: section.icon,
    onClick: () => addSection(place, section.type),
  }))
}

function blockMenu(node) {
  const section = props.editor.locate(node.key).section
  const schema = SECTIONS[section.type]
  const count = section.blocks.length
  const full = schema.max_blocks && count >= schema.max_blocks
  const themeBlocks = Object.entries(schema.blocks ?? {}).map(([type, block]) => ({
    label: block.name,
    icon: block.icon,
    disabled: full,
    onClick: () => addBlock(node.key, type),
  }))
  const appBlocks = schema.accepts_apps
    ? Object.entries(APP_BLOCKS).map(([type, block]) => ({
        label: `${block.name}`,
        icon: block.icon,
        onClick: () => addBlock(node.key, type),
      }))
    : []
  return [
    ...(themeBlocks.length ? [{ group: 'Theme blocks', options: themeBlocks }] : []),
    ...(appBlocks.length ? [{ group: 'Apps', options: appBlocks }] : []),
  ]
}

function rowMenu(node) {
  return [
    { label: 'Duplicate', icon: 'lucide-copy', onClick: () => duplicate(node.key) },
    ...(node.static ? [] : [{ label: 'Remove', icon: 'lucide-trash-2', theme: 'red', onClick: () => remove(node.key) }]),
  ]
}
</script>

<template>
  <div class="space-y-1">
    <button
      class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-base text-ink-gray-8 hover:bg-surface-gray-2"
      :class="{ 'bg-surface-gray-3 font-medium': state.selectedId === 'theme-settings' }"
      data-tree-theme-settings
      @click="select('theme-settings', { scroll: false })"
    >
      <span class="lucide-palette size-4 text-ink-gray-6" aria-hidden="true" />
      Theme settings
    </button>

    <Tree :nodes="nodes" node-key="key" draggable :move="allowMove" guides="lines" @drag-end="onDragEnd">
      <template #item-prefix="{ node }">
        <span v-if="node.icon" :class="[node.icon, node.app ? 'text-ink-violet-4' : 'text-ink-gray-6']" class="size-4 shrink-0" aria-hidden="true" />
      </template>

      <template #item-label="{ node }">
        <span
          v-if="node.kind === 'group'"
          class="text-sm font-semibold uppercase tracking-wide text-ink-gray-5"
        >{{ node.label }}</span>
        <button
          v-else
          class="min-w-0 flex-1 truncate rounded px-1 text-left"
          :class="[
            node.key === state.selectedId ? 'bg-surface-gray-3 font-medium text-ink-gray-9' : 'text-ink-gray-8',
            node.hidden ? 'line-through opacity-50' : '',
          ]"
          :data-tree-node="node.key"
          @click.stop="select(node.key)"
        >
          {{ node.label }}
          <span v-if="node.detail" class="text-ink-gray-5">· {{ node.detail }}</span>
          <span v-if="node.app" class="ml-1 rounded bg-surface-violet-1 px-1 text-xs text-ink-violet-4">{{ node.app }}</span>
        </button>
      </template>

      <template #item-suffix="{ node }">
        <Dropdown v-if="node.kind === 'group'" :options="sectionMenu(node.place)">
          <Button size="sm" variant="ghost" icon="lucide-plus" :label="`Add section to ${node.label}`" :data-add-section="node.place" />
        </Dropdown>
        <!-- Row actions appear on hover or for the selected row, so labels
             keep the width they need to be told apart. -->
        <div
          v-else
          class="items-center group-hover/row:flex focus-within:flex"
          :class="node.key === state.selectedId ? 'flex' : 'hidden'"
        >
          <Dropdown v-if="node.canAddBlocks" :options="blockMenu(node)">
            <Button size="sm" variant="ghost" icon="lucide-plus" label="Add block" :data-add-block="node.key" />
          </Dropdown>
          <Button
            size="sm"
            variant="ghost"
            :icon="node.hidden ? 'lucide-eye-off' : 'lucide-eye'"
            :label="node.hidden ? 'Show' : 'Hide'"
            @click.stop="toggleHidden(node.key)"
          />
          <Dropdown :options="rowMenu(node)">
            <Button size="sm" variant="ghost" icon="lucide-ellipsis" label="More" />
          </Dropdown>
        </div>
      </template>
    </Tree>
  </div>
</template>
