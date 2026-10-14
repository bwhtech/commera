<script setup>
/**
 * Photos for one variant. The first one is the cover — it is what the
 * storefront swaps to when a shopper picks this colour or size.
 */
import { ref } from 'vue'
import { Badge, Button, toast, useFileUpload } from 'frappe-ui'
import { useAdminAction } from '../data/api'

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
      toast.error(`Could not upload ${file.name}`)
    }
  }
  if (!uploaded.length) return

  try {
    await addAction.submit({ style_attribute_variant: props.variant.name, file_urls: uploaded })
  } catch {
    return
  }
  toast.success(`${uploaded.length} photo${uploaded.length > 1 ? 's' : ''} added to ${props.variant.option}`)
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
  try {
    await removeAction.submit({ style_attribute_variant: props.variant.name, file_url: fileUrl })
  } catch {
    return
  }
  emit('saved')
}
</script>

<template>
  <div>
    <input ref="fileInput" type="file" accept="image/*" multiple class="hidden" @change="onFilePicked" />
    <div class="flex flex-wrap gap-2" @dragover.prevent @drop.prevent="onDrop">
      <div
        v-for="(image, index) in variant.images"
        :key="`${index}-${image}`"
        class="group relative size-20 overflow-hidden rounded-4 border border-outline-gray-1 bg-surface-gray-2"
      >
        <img :src="image" class="size-full object-cover" alt="" />
        <Badge v-if="index === 0" class="absolute bottom-1 start-1" label="Cover" theme="gray" variant="solid" size="sm" />
        <!-- Touch has no hover, so the only way to delete a photo has to be
             visible from the start on a phone; hover-reveal is a desktop luxury. -->
        <Button
          class="absolute right-1 top-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100"
          icon="lucide-x"
          label="Remove photo"
          @click="remove(image)"
        />
      </div>

      <button
        class="grid size-20 place-content-center rounded-4 border border-dashed border-outline-gray-2 text-ink-gray-5 hover:bg-surface-gray-1"
        aria-label="Add photo"
        :disabled="isUploading"
        @click="fileInput.click()"
      >
        <span class="flex flex-col items-center gap-1">
          <span :class="isUploading ? 'lucide-loader-2 animate-spin' : 'lucide-plus'" class="size-5" aria-hidden="true" />
          <span class="text-sm">{{ isUploading ? 'Uploading…' : 'Add' }}</span>
        </span>
      </button>
    </div>

    <p v-if="!variant.images.length" class="mt-2 text-p-sm text-ink-gray-5">
      No photo yet. This variant falls back to the product's own image on the storefront.
    </p>
  </div>
</template>
