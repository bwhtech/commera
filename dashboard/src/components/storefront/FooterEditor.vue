<script setup>
import { onMounted, ref } from 'vue'
import { Badge, Button, Dropdown, Skeleton, Tooltip, dialog, toast } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import ChromePreview from './ChromePreview.vue'
import FooterLinkDialog from './FooterLinkDialog.vue'
import { useFooter } from '../../data/footerEditor'
import { errorMessage } from '../../data/errors'
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
  if (moved) toast.success(`Moved to ${target.title}`)
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
    title: 'Add a footer column',
    fields: [{ name: 'title', label: 'Column title', placeholder: 'Help', required: true }],
    confirmLabel: 'Add',
    onConfirm: async ({ values }) => {
      if (await mutate('add_section', { title: values.title.trim() })) toast.success('Column added')
    },
  })
}

function renameSection(section) {
  dialog.prompt({
    title: 'Rename column',
    fields: [{ name: 'title', label: 'Column title', defaultValue: section.title, required: true }],
    confirmLabel: 'Rename',
    onConfirm: async ({ values }) => {
      const renamed = await mutate('rename_section', {
        old_name: section.name,
        new_name: values.title,
      })
      if (renamed) toast.success('Column renamed')
    },
  })
}

function removeSection(section) {
  const count = section.links.length
  dialog.danger({
    title: `Delete "${section.title}"?`,
    message: count
      ? `The ${count} ${count === 1 ? 'link' : 'links'} in this column go with it. Pages are not deleted.`
      : 'Pages are not deleted — only this footer column.',
    confirmLabel: 'Delete column',
    onConfirm: async () => {
      if (await mutate('delete_section', { name: section.name })) toast.success('Column deleted')
    },
  })
}

function removeLink(section, link) {
  dialog.danger({
    title: `Remove "${link.link_label}"?`,
    message: 'The page it points at is not deleted — only this footer link.',
    confirmLabel: 'Remove link',
    onConfirm: async () => {
      const removed = await mutate('delete_link', {
        section_name: section.name,
        link_row_name: link.name,
      })
      if (removed) toast.success('Link removed')
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
    { label: 'Add link', icon: 'lucide-plus', onClick: () => openLinkDialog(section) },
    { label: 'Rename', icon: 'lucide-pencil', onClick: () => renameSection(section) },
    {
      label: 'Move left',
      icon: 'lucide-arrow-left',
      disabled: columnIndex === 0,
      onClick: () => moveSection(columnIndex, -1),
    },
    {
      label: 'Move right',
      icon: 'lucide-arrow-right',
      disabled: columnIndex === sections.value.length - 1,
      onClick: () => moveSection(columnIndex, 1),
    },
    {
      label: section.enabled ? 'Hide from footer' : 'Show in footer',
      icon: section.enabled ? 'lucide-eye-off' : 'lucide-eye',
      onClick: () => toggleSection(section),
    },
    {
      group: 'Danger',
      options: [
        { label: 'Delete column', icon: 'lucide-trash-2', theme: 'red', onClick: () => removeSection(section) },
      ],
    },
  ]
}

function linkActions(section, columnIndex, link, linkIndex) {
  return [
    { label: 'Edit', icon: 'lucide-pencil', onClick: () => openLinkDialog(section, link) },
    {
      label: 'Move up',
      icon: 'lucide-arrow-up',
      disabled: linkIndex === 0,
      onClick: () => moveLinkWithinColumn(section, linkIndex, -1),
    },
    {
      label: 'Move down',
      icon: 'lucide-arrow-down',
      disabled: linkIndex === section.links.length - 1,
      onClick: () => moveLinkWithinColumn(section, linkIndex, 1),
    },
    {
      label: 'Move to previous column',
      icon: 'lucide-arrow-left',
      disabled: columnIndex === 0,
      onClick: () => moveLinkToColumn(section, link, columnIndex, -1),
    },
    {
      label: 'Move to next column',
      icon: 'lucide-arrow-right',
      disabled: columnIndex === sections.value.length - 1,
      onClick: () => moveLinkToColumn(section, link, columnIndex, 1),
    },
    {
      label: link.enabled ? 'Hide from footer' : 'Show in footer',
      icon: link.enabled ? 'lucide-eye-off' : 'lucide-eye',
      onClick: () => toggleLink(section, link),
    },
    {
      group: 'Danger',
      options: [
        { label: 'Remove link', icon: 'lucide-trash-2', theme: 'red', onClick: () => removeLink(section, link) },
      ],
    },
  ]
}
</script>

<template>
  <div>
    <div class="flex items-center justify-end">
      <Button icon-left="lucide-plus" label="Add column" @click="addSection" />
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
      title="Could not load your footer"
      :description="errorMessage(loadError)"
    />

    <EmptyState
      v-else-if="!sections.length"
      icon="lucide-columns-3"
      title="No footer columns yet"
      description="Add a column, then fill it with links to your pages."
    >
      <Button variant="subtle" theme="gray" label="Add column" @click="addSection" />
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

          <Badge v-if="!section.enabled" variant="subtle" theme="amber" label="Hidden" />
          <span class="shrink-0 text-sm text-ink-gray-5">{{ section.links.length }}</span>

          <Tooltip text="Add a link">
            <Button
              variant="ghost"
              class="!size-5 shrink-0"
              aria-label="Add a link to this column"
              @click="openLinkDialog(section)"
            >
              <template #icon>
                <span class="lucide-plus size-4 text-ink-gray-5" aria-hidden="true" />
              </template>
            </Button>
          </Tooltip>

          <Dropdown :options="columnActions(section, columnIndex)">
            <Button variant="ghost" class="!size-5 shrink-0" aria-label="Column actions">
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
              <Badge v-if="!link.enabled" variant="subtle" theme="amber" label="Hidden" />
              <Dropdown :options="linkActions(section, columnIndex, link, linkIndex)">
                <Button variant="ghost" class="!size-5" aria-label="Link actions">
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
            label="Add link"
            @click="openLinkDialog(section)"
          />
        </div>
      </div>
    </div>

    <ChromePreview
      v-model:collapsed="previewCollapsed"
      :token="previewToken"
      path="/footer_editor_preview"
      title="Footer preview"
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

