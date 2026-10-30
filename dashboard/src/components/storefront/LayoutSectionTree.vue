<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Button, Dropdown, Tree } from 'frappe-ui'
import { canAddBlocks, maxBlocks } from '../../data/themeLayout'

const props = defineProps({
  editor: { type: Object, required: true },
})

const emit = defineEmits(['add-section'])

const {
  state,
  schemaByType,
  select,
  addBlock,
  duplicateSection,
  duplicateBlock,
  removeSection,
  removeBlock,
  toggleHidden,
  moveSection,
  moveBlock,
} = props.editor

const PART_LABELS = { header_group: 'Header', footer_group: 'Footer' }

const sectionKey = (group, sectionId) => `section:${group}:${sectionId}`
const blockKey = (group, sectionId, blockId) => `block:${group}:${sectionId}:${blockId}`
const partKey = (group) => `part:${group}`

function translated(value) {
  if (value && typeof value === 'object') return value[state.language] || value.en || ''
  return typeof value === 'string' ? value : ''
}

function detailOf(settings) {
  return translated(settings?.title) || translated(settings?.heading) || ''
}

function sectionNodes(part) {
  return part.layout.sections.map((section) => {
    const schema = schemaByType.value[section.type]
    const full = (section.blocks ?? []).length >= maxBlocks(schema)
    return {
      key: sectionKey(part.group, section.id),
      kind: 'section',
      group: part.group,
      sectionId: section.id,
      label: schema?.name ?? section.type,
      detail: detailOf(section.settings),
      hidden: Boolean(section.hidden),
      canAddBlock: canAddBlocks(schema),
      full,
      blockTypes: Object.entries(schema?.blocks ?? {}),
      children: (section.blocks ?? []).map((block) => ({
        key: blockKey(part.group, section.id, block.id),
        kind: 'block',
        group: part.group,
        sectionId: section.id,
        blockId: block.id,
        label: schema?.blocks?.[block.type]?.name ?? block.type,
        detail: detailOf(block.settings),
        full,
      })),
    }
  })
}

const grouped = computed(() => state.parts.length > 1)

const nodes = computed(() => {
  if (!grouped.value) return state.parts.flatMap(sectionNodes)
  return state.parts.map((part) => ({
    key: partKey(part.group),
    kind: 'part',
    group: part.group,
    label: PART_LABELS[part.group] ?? 'Page',
    children: sectionNodes(part),
  }))
})

const expandedKeys = ref([])

function expand(key) {
  if (!expandedKeys.value.includes(key)) expandedKeys.value = [...expandedKeys.value, key]
}

watch(
  () => state.parts.map((part) => part.group),
  (groups) => groups.forEach((group) => expand(partKey(group))),
  { immediate: true },
)

watch(
  () => state.selection,
  (selection) => {
    if (selection?.kind === 'block') expand(sectionKey(selection.group, selection.section))
    if (selection?.group) expand(partKey(selection.group))
    revealSelectedRow()
  },
  { immediate: true },
)

async function revealSelectedRow() {
  await nextTick()
  document.querySelector('[data-section-tree] [aria-current="true"]')?.scrollIntoView({ block: 'nearest' })
}

function isSelected(node) {
  const selection = state.selection
  if (selection?.kind !== node.kind || selection.group !== node.group) return false
  if (node.kind === 'section') return selection.section === node.sectionId
  return selection.section === node.sectionId && selection.block === node.blockId
}

function selectNode(node) {
  if (node.kind === 'section') select({ kind: 'section', group: node.group, section: node.sectionId })
  else select({ kind: 'block', group: node.group, section: node.sectionId, block: node.blockId })
}

function canDrop({ node, target, position }) {
  if (position === 'inside' || node.kind === 'part' || node.kind !== target.kind) return false
  if (node.group !== target.group) return false
  return node.kind === 'section' || node.sectionId === target.sectionId
}

function onDragEnd(info) {
  if (!info) return
  const { node } = info
  if (node.kind === 'section') moveSection(node.group, node.sectionId, info.newIndex)
  else if (node.kind === 'block') moveBlock(node.group, node.sectionId, node.blockId, info.newIndex)
}

function addBlockOptions(node) {
  return node.blockTypes.map(([type, blockSchema]) => ({
    label: blockSchema.name ?? type,
    icon: 'lucide-plus',
    disabled: node.full,
    onClick: () => {
      addBlock(node.group, node.sectionId, type)
      expand(node.key)
    },
  }))
}

function rowActions(node) {
  if (node.kind === 'block') {
    return [
      {
        label: 'Duplicate',
        icon: 'lucide-copy',
        disabled: node.full,
        onClick: () => duplicateBlock(node.group, node.sectionId, node.blockId),
      },
      {
        label: 'Remove',
        icon: 'lucide-trash-2',
        theme: 'red',
        onClick: () => removeBlock(node.group, node.sectionId, node.blockId),
      },
    ]
  }
  return [
    { label: 'Duplicate', icon: 'lucide-copy', onClick: () => duplicateSection(node.group, node.sectionId) },
    { label: 'Remove', icon: 'lucide-trash-2', theme: 'red', onClick: () => removeSection(node.group, node.sectionId) },
  ]
}
</script>

<template>
  <div class="flex flex-col gap-1" data-section-tree>
    <button
      type="button"
      class="flex w-full items-center gap-2 rounded-5 px-1.5 py-1.5 text-start text-base text-ink-gray-8"
      :class="state.selection?.kind === 'theme' ? 'bg-surface-gray-3 font-medium' : 'hover:bg-surface-gray-2'"
      data-tree-theme-settings
      @click="select({ kind: 'theme' }, { scroll: false })"
    >
      <span class="lucide-palette size-4 text-ink-gray-6" aria-hidden="true" />
      Theme settings
    </button>

    <div v-if="!grouped" class="mt-2 flex items-center justify-between px-2">
      <p class="text-sm text-ink-gray-5">Sections</p>
      <Button
        variant="ghost"
        icon-left="lucide-plus"
        label="Add section"
        @click="emit('add-section', editor.pagePart.value?.group)"
      />
    </div>

    <Tree
      v-model:expanded="expandedKeys"
      :nodes="nodes"
      node-key="key"
      draggable
      guides="lines"
      class="[&_[data-slot=row]:has([aria-current=true])]:bg-surface-gray-3"
      :move="canDrop"
      @drag-end="onDragEnd"
    >
      <template #item-label="{ node }">
        <span v-if="node.kind === 'part'" class="min-w-0 flex-1 truncate text-sm text-ink-gray-5">
          {{ node.label }}
        </span>
        <button
          v-else
          type="button"
          class="min-w-0 flex-1 truncate text-start text-base"
          :class="[isSelected(node) ? 'font-medium' : '', node.hidden ? 'text-ink-gray-4' : 'text-ink-gray-8']"
          :aria-current="isSelected(node) ? 'true' : undefined"
          :data-tree-node="node.key"
          @click.stop="selectNode(node)"
        >
          {{ node.label }}
          <span v-if="node.detail" class="text-ink-gray-5">· {{ node.detail }}</span>
        </button>
      </template>

      <template #item-suffix="{ node }">
        <div v-if="node.kind === 'part'" class="flex shrink-0 items-center" @click.stop>
          <Button
            variant="ghost"
            class="!size-6"
            :aria-label="`Add section to ${node.label}`"
            @click="emit('add-section', node.group)"
          >
            <template #icon>
              <span class="lucide-plus size-4 text-ink-gray-5" aria-hidden="true" />
            </template>
          </Button>
        </div>
        <div
          v-else
          class="shrink-0 items-center focus-within:flex group-hover/row:flex"
          :class="isSelected(node) ? 'flex' : 'hidden'"
          @click.stop
        >
          <Dropdown v-if="node.canAddBlock" :options="addBlockOptions(node)">
            <Button variant="ghost" class="!size-6" :aria-label="`Add block to ${node.label}`">
              <template #icon>
                <span class="lucide-plus size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </Button>
          </Dropdown>
          <Button
            v-if="node.kind === 'section'"
            variant="ghost"
            class="!size-6"
            :aria-label="node.hidden ? `Show ${node.label}` : `Hide ${node.label}`"
            @click="toggleHidden(node.group, node.sectionId)"
          >
            <template #icon>
              <span
                class="size-4 text-ink-gray-5"
                :class="node.hidden ? 'lucide-eye-off' : 'lucide-eye'"
                aria-hidden="true"
              />
            </template>
          </Button>
          <Dropdown :options="rowActions(node)">
            <Button variant="ghost" class="!size-6" :aria-label="`${node.label} actions`">
              <template #icon>
                <span class="lucide-ellipsis size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </Button>
          </Dropdown>
        </div>
      </template>
    </Tree>
  </div>
</template>
