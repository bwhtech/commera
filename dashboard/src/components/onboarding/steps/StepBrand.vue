<script setup>
import { ref } from 'vue'
import { Button, Spinner, toast, useFileUpload } from 'frappe-ui'
import { __ } from '../../../data/translation'
import { draft } from '../../../ia/onboarding'

const { upload, isUploading } = useFileUpload()
const fileInput = ref(null)

async function uploadLogo(event) {
  const [file] = [...(event.target.files ?? [])]
  event.target.value = ''
  if (!file) return
  try {
    // Public, the same as Settings' brand logo: it is drawn in storefront markup for every shopper.
    const uploaded = await upload(file, { private: false })
    draft.brandLogo = uploaded.file_url
  } catch {
    toast.error(__('Could not upload {0}', [file.name]))
  }
}
</script>

<template>
  <div class="space-y-6">
    <input ref="fileInput" type="file" accept="image/*" class="hidden" data-onboarding-logo-input @change="uploadLogo" />
    <button
      type="button"
      class="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-5 border border-dashed border-outline-gray-3 text-ink-gray-5 transition-[background-color,transform] duration-150 ease-out-strong hover:bg-surface-gray-1 active:scale-[0.99]"
      :disabled="isUploading"
      @click="fileInput?.click()"
    >
      <Spinner v-if="isUploading" class="size-5" />
      <img v-else-if="draft.brandLogo" :src="draft.brandLogo" :alt="__('Your logo')" class="max-h-16 max-w-[60%] object-contain" />
      <template v-else>
        <span class="lucide-image-plus size-6" aria-hidden="true" />
        <span class="text-sm">{{ __('Logo') }}</span>
      </template>
    </button>
    <Button v-if="draft.brandLogo" variant="ghost" size="sm" :label="__('Remove logo')" class="-mt-4" @click="draft.brandLogo = ''" />
  </div>
</template>
