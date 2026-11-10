<script setup>
import { onMounted, ref } from 'vue'
import { Badge, Button, Dropdown, Skeleton, Tooltip, dialog, toast } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import ChromePreview from './ChromePreview.vue'
import FooterLinkDialog from './FooterLinkDialog.vue'
import { useFooter } from '../../data/footerEditor'
import { errorMessage } from '../../data/errors'
import { __ } from '../../data/translation'
import { useIsMobile } from '../../utils/useIsMobile'

const { sections, pages, loadError, previewToken, loading, load, mutate, reordered } = useFooter()

onMounted(load)

// A 1440px preview scaled to ~26% is illegible on a phone, and real data weight.
const isMobile = useIsMobile()
const previewCollapsed = ref(isMobile.value)
const linkDialogOpen = ref(false)
const linkDialogSection = ref(null)
const linkDialogLink = ref(null)

async function moveLinkWithinColumn(section, linkIndex, offset) {
  await mutate('reorder_links', {
    section_name: section.name,
    ordered_row_names: reordered(
      section.links.map((link) => link.name),
      linkIndex,
      linkIndex + offset,
    ),
  })
}

async function moveLinkToColumn(section, link, columnIndex, offset) {
  const target = sections.value[columnIndex + offset]
  if (!target) return
  const moved = await mutate('move_link', {
    from_section: section.name,
    to_section: target.name,
    link_row_name: link.name,
    target_index: target.links.length,
  })
  if (moved) toast.success(__('Moved to {0}', [target.title]))
}

async function moveSection(columnIndex, offset) {
  await mutate('reorder_sections', {
    ordered_names: reordered(
      sections.value.map((section) => section.name),
      columnIndex,
      columnIndex + offset,
    ),
  })
}

function addSection() {
  dialog.prompt({
    title: __('Add a footer column'),
    fields: [{ name: 'title', label: __('Column title'), placeholder: __('Help'), required: true }],
    confirmLabel: __('Add'),
    onConfirm: async ({ values }) => {
      if (await mutate('add_section', { title: values.title.trim() })) toast.success(__('Column added'))
    },
  })
}

function renameSection(section) {
  dialog.prompt({
    title: __('Rename column'),
    fields: [{ name: 'title', label: __('Column title'), defaultValue: section.title, required: true }],
    confirmLabel: __('Rename'),
    onConfirm: async ({ values }) => {
      const renamed = await mutate('rename_section', {
        old_name: section.name,
        new_name: values.title,
      })
      if (renamed) toast.success(__('Column renamed'))
    },
  })
}

function removeSection(section) {
  const count = section.links.length
  dialog.danger({
    title: __('Delete "{0}"?', [section.title]),
    message: count
      ? count === 1
        ? __('The 1 link in this column goes with it. Pages are not deleted.')
        : __('The {0} links in this column go with it. Pages are not deleted.', [count])
      : __('Pages are not deleted — only this footer column.'),
    confirmLabel: __('Delete column'),
    onConfirm: async () => {
      if (await mutate('delete_section', { name: section.name })) toast.success(__('Column deleted'))
    },
  })
}

function removeLink(section, link) {
  dialog.danger({
    title: __('Remove "{0}"?', [link.link_label]),
    message: __('The page it points at is not deleted — only this footer link.'),
    confirmLabel: __('Remove link'),
    onConfirm: async () => {
      const removed = await mutate('delete_link', {
        section_name: section.name,
        link_row_name: link.name,
      })
      if (removed) toast.success(__('Link removed'))
    },
  })
}

function openLinkDialog(section, link = null) {
  linkDialogSection.value = section
  linkDialogLink.value = link
  linkDialogOpen.value = true
}

async function saveLink({ label, url }) {
  const section = linkDialogSection.value
  const link = linkDialogLink.value
  if (!section) return false

  const saved = link
    ? await mutate('update_link', {
        section_name: section.name,
        link_row_name: link.name,
        label,
        url,
      })
    : await mutate('add_link', { section_name: section.name, label, url })
  return Boolean(saved)
}

async function toggleSection(section) {
  await mutate('set_section_enabled', { name: section.name, enabled: section.enabled ? 0 : 1 })
}

async function toggleLink(section, link) {
  await mutate('set_link_enabled', {
    section_name: section.name,
    link_row_name: link.name,
    enabled: link.enabled ? 0 : 1,
  })
}

function columnActions(section, columnIndex) {
  return [
    { label: __('Add link'), icon: 'lucide-plus', onClick: () => openLinkDialog(section) },
    { label: __('Rename'), icon: 'lucide-pencil', onClick: () => renameSection(section) },
    {
      label: __('Move left'),
      icon: 'lucide-arrow-left',
      disabled: columnIndex === 0,
      onClick: () => moveSection(columnIndex, -1),
    },
    {
      label: __('Move right'),
      icon: 'lucide-arrow-right',
      disabled: columnIndex === sections.value.length - 1,
      onClick: () => moveSection(columnIndex, 1),
    },
    {
      label: section.enabled ? __('Hide from footer') : __('Show in footer'),
      icon: section.enabled ? 'lucide-eye-off' : 'lucide-eye',
      onClick: () => toggleSection(section),
    },
    {
      group: __('Danger'),
      options: [
        { label: __('Delete column'), icon: 'lucide-trash-2', theme: 'red', onClick: () => removeSection(section) },
      ],
    },
  ]
}

function linkActions(section, columnIndex, link, linkIndex) {
  return [
    { label: __('Edit'), icon: 'lucide-pencil', onClick: () => openLinkDialog(section, link) },
    {
      label: __('Move up'),
      icon: 'lucide-arrow-up',
      disabled: linkIndex === 0,
      onClick: () => moveLinkWithinColumn(section, linkIndex, -1),
    },
    {
      label: __('Move down'),
      icon: 'lucide-arrow-down',
      disabled: linkIndex === section.links.length - 1,
      onClick: () => moveLinkWithinColumn(section, linkIndex, 1),
    },
    {
      label: __('Move to previous column'),
      icon: 'lucide-arrow-left',
      disabled: columnIndex === 0,
      onClick: () => moveLinkToColumn(section, link, columnIndex, -1),
    },
    {
      label: __('Move to next column'),
      icon: 'lucide-arrow-right',
      disabled: columnIndex === sections.value.length - 1,
      onClick: () => moveLinkToColumn(section, link, columnIndex, 1),
    },
    {
      label: link.enabled ? __('Hide from footer') : __('Show in footer'),
      icon: link.enabled ? 'lucide-eye-off' : 'lucide-eye',
      onClick: () => toggleLink(section, link),
    },
    {
      group: __('Danger'),
      options: [
        { label: __('Remove link'), icon: 'lucide-trash-2', theme: 'red', onClick: () => removeLink(section, link) },
      ],
    },
  ]
}
</script>

<template>
  <div>
    <div class="flex items-center justify-end">
      <Button icon-left="lucide-plus" :label="__('Add column')" @click="addSection" />
    </div>

    <div
      v-if="loading && !sections.length"
      class="mt-3 flex items-start gap-3 overflow-x-auto pb-2"
      aria-hidden="true"
    >
      <div
        v-for="column in 3"
        :key="column"
        class="flex w-72 shrink-0 flex-col rounded-6 border border-outline-gray-1 bg-surface-gray-1"
      >
        <div class="flex items-center gap-2 px-2 py-2">
          <Skeleton class="h-4 w-28 rounded-4" />
          <Skeleton class="ms-auto h-3.5 w-4 rounded-4" />
        </div>
        <div class="flex min-h-16 flex-col gap-2 px-2 pb-2">
          <div
            v-for="link in 3"
            :key="link"
            class="rounded-5 border border-outline-gray-1 bg-surface-base px-2 py-2 shadow-sm"
          >
            <Skeleton class="h-4 w-32 rounded-4" />
            <Skeleton class="mt-1.5 h-3.5 w-44 rounded-4" />
          </div>
        </div>
      </div>
    </div>

    <EmptyState
      v-else-if="loadError"
      icon="lucide-triangle-alert"
      :title="__('Could not load your footer')"
      :description="errorMessage(loadError)"
    />

    <EmptyState
      v-else-if="!sections.length"
      icon="lucide-columns-3"
      :title="__('No footer columns yet')"
      :description="__('Add a column, then fill it with links to your pages.')"
    >
      <Button variant="subtle" theme="gray" :label="__('Add column')" @click="addSection" />
    </EmptyState>

    <div v-else class="mt-3 flex items-start gap-3 overflow-x-auto pb-2">
      <div
        v-for="(section, columnIndex) in sections"
        :key="section.name"
        class="flex w-72 shrink-0 flex-col rounded-6 border border-outline-gray-1 bg-surface-gray-1"
      >
        <div class="flex items-center gap-2 px-2 py-2">
          <span
            class="min-w-0 flex-1 truncate text-base font-medium"
            :class="section.enabled ? 'text-ink-gray-8' : 'text-ink-gray-4'"
          >
            {{ section.title }}
          </span>

          <Badge v-if="!section.enabled" variant="subtle" :label="__('Hidden')" theme="amber" />
          <span class="shrink-0 text-sm text-ink-gray-5">{{ section.links.length }}</span>

          <Tooltip :text="__('Add a link')">
            <Button
              variant="ghost"
              class="!size-5 shrink-0"
              :aria-label="__('Add a link to this column')"
              @click="openLinkDialog(section)"
            >
              <template #icon>
                <span class="lucide-plus size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </Button>
          </Tooltip>

          <Dropdown :options="columnActions(section, columnIndex)">
            <Button variant="ghost" class="!size-5 shrink-0" :aria-label="__('Column actions')">
              <template #icon>
                <span class="lucide-ellipsis size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </Button>
          </Dropdown>
        </div>

        <div class="flex min-h-16 flex-col gap-2 px-2 pb-2">
          <div
            v-for="(link, linkIndex) in section.links"
            :key="link.name"
            class="flex items-start gap-2 rounded-5 border border-outline-gray-1 bg-surface-base px-2 py-2 shadow-sm"
          >
            <button
              type="button"
              class="min-w-0 flex-1 text-start"
              @click="openLinkDialog(section, link)"
            >
              <span
                class="block truncate text-base"
                :class="link.enabled ? 'text-ink-gray-8' : 'text-ink-gray-4'"
              >
                {{ link.link_label }}
              </span>
              <span class="mt-0.5 block truncate text-sm text-ink-gray-5">{{ link.link_url }}</span>
            </button>

            <div class="flex shrink-0 items-center gap-1">
              <Badge v-if="!link.enabled" variant="subtle" :label="__('Hidden')" theme="amber" />
              <Dropdown :options="linkActions(section, columnIndex, link, linkIndex)">
                <Button variant="ghost" class="!size-5" :aria-label="__('Link actions')">
                  <template #icon>
                    <span class="lucide-ellipsis size-4 text-ink-gray-5" aria-hidden="true" />
                  </template>
                </Button>
              </Dropdown>
            </div>
          </div>
        </div>

        <div class="px-2 pb-2">
          <Button
            class="w-full"
            variant="ghost"
            theme="gray"
            icon-left="lucide-plus"
            :label="__('Add link')"
            @click="openLinkDialog(section)"
          />
        </div>
      </div>
    </div>

    <ChromePreview
      v-model:collapsed="previewCollapsed"
      :token="previewToken"
      path="/footer_editor_preview"
      :title="__('Footer preview')"
      selector="footer"
    />

    <FooterLinkDialog
      v-model:open="linkDialogOpen"
      :section="linkDialogSection"
      :link="linkDialogLink"
      :pages="pages"
      :submit="saveLink"
    />
  </div>
</template>

