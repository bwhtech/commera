<script setup>
/**
 * Photos for one color. The first one is the cover: it is what the
 * storefront swaps to when a shopper picks this color.
 */
import { computed, ref } from 'vue'
import { Badge, Button, Dropdown, toast, useFileUpload } from 'frappe-ui'
import { useAdminAction, trySubmit } from '../data/api'
import { PLACEHOLDER_OPTION } from '../data/product'
import { __ } from '../data/translation'

const props = defineProps({
  variant: { type: Object, required: true },
})
const emit = defineEmits(['saved'])

const { upload, isUploading } = useFileUpload()
const addAction = useAdminAction('catalog.add_product_images')
const removeAction = useAdminAction('catalog.remove_product_image')
const moveAction = useAdminAction('catalog.move_product_image')

const isPlaceholder = computed(() => props.variant.option === PLACEHOLDER_OPTION)

const fileInput = ref(null)
const lastRemoved = ref(null)

async function addFiles(files) {
  lastRemoved.value = null
  const uploaded = []
  for (const file of files) {
    try {
      // Public: these are storefront product photos, not access-controlled files.
      const result = await upload(file, { private: false })
      uploaded.push(result.file_url)
    } catch {
      toast.error(__('Could not upload {0}', [file.name]))
    }
  }
  if (!uploaded.length) return

  const added = await trySubmit(addAction, { style_attribute_variant: props.variant.name, file_urls: uploaded })
  if (!added) return
  toast.success(addedMessage(uploaded.length))
  emit('saved')
}

function addedMessage(count) {
  if (isPlaceholder.value) return count === 1 ? __('1 photo added') : __('{0} photos added', [count])
  return count === 1
    ? __('1 photo added to {0}', [props.variant.option])
    : __('{0} photos added to {1}', [count, props.variant.option])
}

function onFilePicked(event) {
  const files = [...(event.target.files ?? [])]
  event.target.value = ''
  if (files.length) addFiles(files)
}

function onDrop(event) {
  addFiles([...(event.dataTransfer?.files ?? [])])
}

async function makeCover(fileUrl) {
  lastRemoved.value = null
  const moved = await trySubmit(moveAction, { style_attribute_variant: props.variant.name, file_url: fileUrl, position: 0 })
  if (!moved) return
  toast.success(__('Cover photo changed'))
  emit('saved')
}

// Removal saves at once, so the way back sits under the photos: the same file, re-attached at its
// old place. Inline rather than a toast action, because a modal dialog blocks clicks on the toast.

async function undoRemove() {
  const { fileUrl, position } = lastRemoved.value
  const added = await trySubmit(addAction, { style_attribute_variant: props.variant.name, file_urls: [fileUrl] })
  if (!added) return
  lastRemoved.value = null
  await trySubmit(moveAction, { style_attribute_variant: props.variant.name, file_url: fileUrl, position })
  emit('saved')
}

async function remove(fileUrl, position) {
  const removed = await trySubmit(removeAction, {
    style_attribute_variant: props.variant.name,
    file_url: fileUrl,
  })
  if (!removed) return
  lastRemoved.value = { fileUrl, position }
  emit('saved')
}

function photoActions(image, index) {
  return [
    index > 0 && { label: __('Make cover'), icon: 'lucide-star', onClick: () => makeCover(image) },
    { label: __('Remove'), icon: 'lucide-trash-2', onClick: () => remove(image, index) },
  ].filter(Boolean)
}
</script>

<template>
  <div>
    <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFilePicked" />
    <button
      v-if="!variant.images.length"
      class="flex min-h-20 w-full flex-col items-center justify-center gap-2 rounded-4 border border-dashed border-outline-gray-2 px-4 py-4 text-center hover:bg-surface-gray-1"
      :disabled="isUploading"
      @click="fileInput.click()"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <span class="grid size-8 shrink-0 place-content-center rounded-full bg-surface-gray-2">
        <span
          :class="isUploading ? 'lucide-loader-2 animate-spin' : 'lucide-image-plus'"
          class="size-4 text-ink-gray-6"
          aria-hidden="true"
        />
      </span>
      <span>
        <span class="block text-base-medium text-ink-gray-8">
          <template v-if="isUploading">{{ __('Uploading…') }}</template>
          <template v-else-if="isPlaceholder">{{ __('Add photos') }}</template>
          <template v-else>{{ __('Add photos of {0}', [variant.option]) }}</template>
        </span>
        <span class="block text-p-sm text-ink-gray-5">
          {{
            isPlaceholder
              ? __('Drop images here or click to choose.')
              : __('Shown when a shopper picks {0}. Drop images here or click to choose.', [variant.option])
          }}
        </span>
      </span>
    </button>
    <div v-else class="flex flex-wrap gap-2" @dragover.prevent @drop.prevent="onDrop">
      <div
        v-for="(image, index) in variant.images"
        :key="`${index}-${image}`"
        class="group relative size-20 overflow-hidden rounded-4 border border-outline-gray-1 bg-surface-gray-2"
      >
        <img :src="image" class="size-full object-cover" alt="" />
        <Badge v-if="index === 0" class="absolute bottom-1 start-1" :label="__('Cover')" theme="gray" variant="solid" size="sm" />
        <!-- Touch has no hover, so on a phone the menu is visible from the start; from sm up it
             shows on hover and on keyboard focus, never invisible while focused. -->
        <Dropdown :options="photoActions(image, index)">
          <Button
            class="absolute end-1 top-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
            size="sm"
            variant="outline"
            icon="lucide-ellipsis"
            :label="__('Photo actions')"
          />
        </Dropdown>
      </div>

      <button
        class="grid size-20 place-content-center rounded-4 border border-dashed border-outline-gray-2 text-ink-gray-5 hover:bg-surface-gray-1"
        :aria-label="__('Add photo')"
        :disabled="isUploading"
        @click="fileInput.click()"
      >
        <span class="flex flex-col items-center gap-1">
          <span :class="isUploading ? 'lucide-loader-2 animate-spin' : 'lucide-plus'" class="size-5" aria-hidden="true" />
          <span class="text-sm">{{ isUploading ? __('Uploading…') : __('Add') }}</span>
        </span>
      </button>
    </div>
    <p v-if="lastRemoved" class="mt-2 flex items-center gap-2 text-p-sm text-ink-gray-6" aria-live="polite">
      {{ __('Photo removed.') }}
      <Button size="sm" variant="ghost" :label="__('Undo')" :loading="addAction.loading" @click="undoRemove" />
    </p>
  </div>
</template>
