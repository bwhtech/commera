<script setup>
import { computed, ref } from 'vue'
import { Button, Spinner, toast, useFileUpload } from 'frappe-ui'
import { BRAND_COLOURS, draft } from '../../../ia/onboarding'
import SwatchDot from '../../SwatchDot.vue'

const { upload, isUploading } = useFileUpload()
const fileInput = ref(null)

// A colour picked earlier in Settings stays on offer, so revisiting never silently drops it.
const colours = computed(() =>
  draft.primaryColor && !BRAND_COLOURS.includes(draft.primaryColor) ? [draft.primaryColor, ...BRAND_COLOURS] : BRAND_COLOURS,
)

async function uploadLogo(event) {
  const [file] = [...(event.target.files ?? [])]
  event.target.value = ''
  if (!file) return
  try {
    // Public, the same as Settings' brand logo: it is drawn in storefront markup for every shopper.
    const uploaded = await upload(file, { private: false })
    draft.brandLogo = uploaded.file_url
  } catch {
    toast.error(`Could not upload ${file.name}`)
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
      <img v-else-if="draft.brandLogo" :src="draft.brandLogo" alt="Your logo" class="max-h-16 max-w-[60%] object-contain" />
      <template v-else>
        <span class="lucide-image-plus size-6" aria-hidden="true" />
        <span class="text-sm">Logo</span>
      </template>
    </button>
    <Button v-if="draft.brandLogo" variant="ghost" size="sm" label="Remove logo" class="-mt-4" @click="draft.brandLogo = ''" />

    <div>
      <p class="mb-2 text-xs text-ink-gray-6">Colour</p>
      <div class="flex flex-wrap items-center gap-2.5">
        <!-- The padding is the gap inside the selection ring: ring-offset paints a fixed white,
             which shows as a halo on a dark dashboard. -->
        <button
          v-for="colour in colours"
          :key="colour"
          type="button"
          class="rounded-full p-0.5 transition-[transform,box-shadow] duration-150 ease-out-strong active:scale-90"
          :class="{ 'ring-2 ring-outline-gray-5': draft.primaryColor === colour }"
          :aria-label="`Use ${colour}`"
          :aria-pressed="draft.primaryColor === colour"
          data-onboarding-colour
          @click="draft.primaryColor = draft.primaryColor === colour ? '' : colour"
        >
          <SwatchDot :color="colour" size="lg" />
        </button>
      </div>
    </div>
  </div>
</template>
