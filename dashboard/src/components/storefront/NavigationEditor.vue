<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dropdown, Skeleton, Tree, dialog, toast } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import CascadePublishDialog from './CascadePublishDialog.vue'
import ChromePreview from './ChromePreview.vue'
import NavInspector from './NavInspector.vue'
import { useNavMenu } from '../../data/navMenu'
import { useAdminRead } from '../../data/api'
import { errorMessage } from '../../data/errors'
import { useIsMobile } from '../../utils/useIsMobile'

const {
  menu,
  loadError,
  selected,
  selectedName,
  findNode,
  loading,
  load,
  call,
  mutate,
  depthOf,
  canNest,
  revision,
} = useNavMenu()

const isMobile = useIsMobile()
const previewCollapsed = ref(isMobile.value)

const itemGroups = useAdminRead('navigation.get_link_options', {
  params: () => ({ doctype: 'Item Group' }),
})

const itemGroupOptions = computed(() => itemGroups.data ?? [])

onMounted(load)

// Tree takes no generic, so its slot, move and drag-end nodes arrive as its opaque
// shape and are tracked by key.
function isMenuNode(node) {
  return findNode(String(node.name)) !== null
}

// Tree already rejects dropping onto itself or into its own descendant; only the
// depth question is left.
function canDrop({ node, target, position }) {
  if (!isMenuNode(node)) return false
  const targetDepth = depthOf(String(target.name))
  const parentDepth = position === 'inside' ? targetDepth : targetDepth - 1
  return canNest(node, parentDepth)
}

async function onDragEnd(info) {
  if (!info) return

  const toParent = info.to === null ? '' : String(info.to)
  const moved = await mutate(
    'move_node',
    { name: String(info.node.name), to_parent: toParent, target_index: info.newIndex },
    toParent,
  )
  if (!moved) await load()
}

function addEntry(parent = '') {
  dialog.prompt({
    title: parent ? 'Add an entry inside' : 'Add a menu section',
    fields: [{ name: 'display_name', label: 'Menu label', placeholder: 'Shoes', required: true }],
    confirmLabel: 'Add',
    onConfirm: async ({ values }) => {
      const added = await mutate(
        'add_node',
        { parent, display_name: values.display_name.trim() },
        parent,
      )
      if (added) toast.success('Menu entry added')
    },
  })
}

function groupCount(node) {
  const total = node.item_groups.length
  if (!total) return ''
  return `${total} ${total === 1 ? 'group' : 'groups'}`
}

function countEntries(nodes) {
  return nodes.reduce((total, node) => total + 1 + countEntries(node.children), 0)
}

function importGroups() {
  const parent = selectedName.value ?? ''
  dialog.prompt({
    title: 'Build the menu from item groups',
    message: parent
      ? `Entries will be added inside "${selected.value?.label}".`
      : 'Entries will be added as new top-level sections.',
    fields: [
      {
        name: 'item_group',
        label: 'Item group',
        type: 'combobox',
        options: itemGroupOptions.value,
        required: true,
        description: 'The group and everything under it, as far as the menu depth allows.',
      },
    ],
    confirmLabel: 'Import',
    onConfirm: async ({ values }) => {
      const before = countEntries(menu.value)
      const imported = await mutate('import_from_item_group', {
        item_group: values.item_group,
        parent,
      })
      if (!imported) return
      const added = countEntries(menu.value) - before
      toast.success(
        added ? `Added ${added} menu ${added === 1 ? 'entry' : 'entries'}` : 'Nothing new to add',
      )
    },
  })
}

async function removeEntry(node) {
  const preview = await call('get_delete_preview', { name: node.name })
  if (!preview) return

  dialog.danger({
    title: `Delete "${preview.label}"?`,
    message: preview.count
      ? `This also removes ${preview.count} ${preview.count === 1 ? 'entry' : 'entries'} nested inside it. Products are not deleted.`
      : 'Products are not deleted — only this menu entry.',
    onConfirm: async () => {
      if (await mutate('delete_node', { name: node.name })) toast.success('Menu entry deleted')
    },
  })
}

async function clearMenu() {
  const preview = await call('get_delete_all_preview')
  if (!preview) return

  dialog.danger({
    title: 'Delete the whole menu?',
    message: `All ${preview.count} entries are removed and shoppers lose the navigation until you build it again. Products are not deleted.`,
    confirmLabel: 'Delete everything',
    onConfirm: async () => {
      if (await mutate('delete_all_nodes')) toast.success('Menu cleared')
    },
  })
}

async function toggleVisible(node) {
  await mutate('set_visibility', { name: node.name, visible: node.visible ? 0 : 1 })
}

const publishTarget = ref(null)
const publishDialogOpen = ref(false)

// Same preview-then-confirm shape as removeEntry: the server counts what would change, and the
// dialog names that count before anything is written.
async function publishProducts(node, publish) {
  const preview = await call('get_publish_preview', { name: node.name, publish })
  if (!preview) return

  publishTarget.value = { name: node.name, label: preview.label, publish, count: preview.count }
  publishDialogOpen.value = true
}

// Same shape Tree's own drag-end path uses (onDragEnd above) — the touch-friendly
// fallback for reordering, since HTML5 drag-and-drop never fires on a phone.
function locateNode(name, nodes = menu.value, parentName = '') {
  for (let index = 0; index < nodes.length; index++) {
    const node = nodes[index]
    if (node.name === name) return { siblings: nodes, index, parentName }
    const found = locateNode(name, node.children, node.name)
    if (found) return found
  }
  return null
}

async function moveEntry(node, offset) {
  const location = locateNode(node.name)
  if (!location) return
  const targetIndex = location.index + offset
  if (targetIndex < 0 || targetIndex >= location.siblings.length) return

  const moved = await mutate(
    'move_node',
    { name: String(node.name), to_parent: location.parentName, target_index: targetIndex },
    location.parentName,
  )
  if (!moved) await load()
}

function rowActions(node) {
  const location = locateNode(node.name)
  const isFirst = !location || location.index === 0
  const isLast = !location || location.index === location.siblings.length - 1

  return [
    { label: 'Add entry inside', icon: 'lucide-corner-down-right', onClick: () => addEntry(node.name) },
    {
      label: 'Move up',
      icon: 'lucide-arrow-up',
      disabled: isFirst,
      onClick: () => moveEntry(node, -1),
    },
    {
      label: 'Move down',
      icon: 'lucide-arrow-down',
      disabled: isLast,
      onClick: () => moveEntry(node, 1),
    },
    {
      label: node.visible ? 'Hide from menu' : 'Show in menu',
      icon: node.visible ? 'eye-off' : 'eye',
      onClick: () => toggleVisible(node),
    },
    // A separate group because it acts on a different object: the rows above move and hide the
    // menu entry, these two publish and unpublish the products filed under it.
    {
      group: 'Products under this entry',
      options: [
        {
          label: 'Publish to the storefront',
          icon: 'lucide-globe',
          onClick: () => publishProducts(node, 1),
        },
        {
          label: 'Take off the storefront',
          icon: 'lucide-globe-lock',
          onClick: () => publishProducts(node, 0),
        },
      ],
    },
    {
      group: 'Danger',
      options: [
        { label: 'Delete', icon: 'lucide-trash-2', theme: 'red', onClick: () => removeEntry(node) },
      ],
    },
  ]
}

const menuActions = computed(() => [
  { label: 'Import from item groups', icon: 'lucide-download', onClick: importGroups },
  {
    group: 'Danger',
    options: [
      { label: 'Delete whole menu', icon: 'lucide-trash-2', theme: 'red', onClick: clearMenu },
    ],
  },
])
</script>

<template>
  <div>
    <div class="flex items-center justify-end gap-2">
      <Button icon-left="lucide-plus" label="Add section" @click="addEntry('')" />
      <Dropdown :options="menuActions">
        <Button icon="lucide-ellipsis" aria-label="Menu actions" />
      </Dropdown>
    </div>

    <div v-if="loading && !menu.length" class="mt-3 gap-6 lg:flex" aria-hidden="true">
      <div class="min-w-0 flex-1">
        <div
          v-for="(row, index) in [
            { indent: '', width: 'w-32' },
            { indent: 'ps-6', width: 'w-40' },
            { indent: 'ps-6', width: 'w-28' },
            { indent: '', width: 'w-36' },
            { indent: 'ps-6', width: 'w-24' },
            { indent: '', width: 'w-32' },
          ]"
          :key="index"
          class="flex h-8 items-center gap-2"
          :class="row.indent"
        >
          <Skeleton class="h-4 rounded-4" :class="row.width" />
          <Skeleton class="ms-auto h-3.5 w-10 shrink-0 rounded-4" />
        </div>
      </div>

      <aside class="mt-8 w-full shrink-0 rounded-6 border border-outline-gray-1 p-4 lg:mt-0 lg:w-[24rem]">
        <Skeleton class="h-5 w-32 rounded-4" />
        <div v-for="field in 3" :key="field" class="mt-4">
          <Skeleton class="h-3.5 w-24 rounded-4" />
          <Skeleton class="mt-1.5 h-7 w-full rounded-4" />
        </div>
      </aside>
    </div>

    <EmptyState
      v-else-if="loadError"
      icon="lucide-triangle-alert"
      title="Could not load your menu"
      :description="errorMessage(loadError)"
    />

    <template v-else>
      <EmptyState
        v-if="!menu.length"
        icon="lucide-list-tree"
        title="No menu yet"
        description="Add a section, or build one from your item groups."
      >
        <Button variant="subtle" theme="gray" label="Import from item groups" @click="importGroups" />
      </EmptyState>

      <div v-else class="mt-3 gap-6 lg:flex">
        <div class="min-w-0 flex-1">
          <Tree :nodes="menu" node-key="name" draggable :move="canDrop" @drag-end="onDragEnd">
            <template #item-label="{ node }">
              <button
                v-if="isMenuNode(node)"
                type="button"
                class="min-w-0 flex-1 truncate text-start text-base"
                :class="[
                  node.visible ? 'text-ink-gray-8' : 'text-ink-gray-4',
                  selectedName === node.name ? 'font-medium' : '',
                ]"
                @click.stop="selectedName = node.name"
              >
                {{ node.label }}
              </button>
            </template>

            <template #item-suffix="{ node }">
              <div v-if="isMenuNode(node)" class="flex items-center gap-2">
                <Badge v-if="!node.visible" variant="subtle" theme="amber" label="Hidden" />
                <span class="w-16 shrink-0 text-end text-sm text-ink-gray-5">{{ groupCount(node) }}</span>
                <span @click.stop>
                  <Dropdown :options="rowActions(node)">
                    <Button variant="ghost" class="!size-5 shrink-0" aria-label="Entry actions">
                      <template #icon>
                        <span class="lucide-ellipsis size-4 text-ink-gray-5" aria-hidden="true" />
                      </template>
                    </Button>
                  </Dropdown>
                </span>
              </div>
            </template>
          </Tree>
        </div>

        <aside
          class="mt-8 w-full shrink-0 rounded-6 border border-outline-gray-1 lg:mt-0 lg:w-[24rem]"
        >
          <NavInspector @remove="removeEntry" />
        </aside>
      </div>
    </template>

    <CascadePublishDialog v-model:open="publishDialogOpen" :target="publishTarget" />

    <ChromePreview
      v-model:collapsed="previewCollapsed"
      :token="revision"
      path="/navbar_editor_preview"
      title="Navigation preview"
      selector="header"
    />
  </div>
</template>

