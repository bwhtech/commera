<script setup>
/**
 * Photos for one variant. The first one is the cover — it is what the
 * storefront swaps to when a shopper picks this colour or size.
 */
import { ref } from 'vue'
import { Badge, Button, toast, useFileUpload } from 'frappe-ui'
import { useAdminAction, trySubmit } from '../data/api'
import { __ } from '../data/translation'

const props = defineProps({
  variant: { type: Object, required: true },
})
const emit = defineEmits(['saved'])

const { upload, isUploading } = useFileUpload()
const addAction = useAdminAction('catalog.add_product_images')
const removeAction = useAdminAction('catalog.remove_product_image')

const fileInput = ref(null)

async function addFiles(files) {
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
  toast.success(
    uploaded.length === 1
      ? __('1 photo added to {0}', [props.variant.option])
      : __('{0} photos added to {1}', [uploaded.length, props.variant.option]),
  )
  emit('saved')
}

function onFilePicked(event) {
  const files = [...(event.target.files ?? [])]
  event.target.value = ''
  if (files.length) addFiles(files)
}

function onDrop(event) {
  addFiles([...(event.dataTransfer?.files ?? [])])
}

async function remove(fileUrl) {
  const removed = await trySubmit(removeAction, {
    style_attribute_variant: props.variant.name,
    file_url: fileUrl,
  })
  if (!removed) return
  emit('saved')
}
</script>

<template>
  <div>
    <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFilePicked" />
    <button
      v-if="!variant.images.length"
      class="flex min-h-20 w-full items-center justify-center gap-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-3 text-start hover:bg-surface-gray-1"
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
          {{ isUploading ? __('Uploading…') : __('Add photos of {0}', [variant.option]) }}
        </span>
        <span class="block text-p-sm text-ink-gray-5">
          {{ __('Shown when a shopper picks {0}. Drop images here or click to choose.', [variant.option]) }}
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
        <!-- Touch has no hover, so the only way to delete a photo has to be
             visible from the start on a phone; hover-reveal is a desktop luxury. -->
        <Button
          class="absolute end-1 top-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100"
          icon="lucide-x"
          :label="__('Remove photo')"
          @click="remove(image)"
        />
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
  </div>
</template>
