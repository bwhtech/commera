<script setup>
import { Dialog } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { DISCOUNT_TYPES } from '../../data/discounts'

const open = defineModel('open', { type: Boolean, default: false })
const router = useRouter()

function choose(slug) {
  open.value = false
  router.push({ name: 'DiscountNew', params: { type: slug } })
}
</script>

<template>
  <Dialog v-model:open="open" title="Create a discount" size="lg">
    <div class="divide-y divide-outline-gray-1">
      <button
        v-for="type in DISCOUNT_TYPES"
        :key="type.slug"
        type="button"
        class="flex w-full items-start gap-3 rounded-4 px-2 py-3 text-left hover:bg-surface-gray-2"
        @click="choose(type.slug)"
      >
        <span class="mt-0.5 rounded-4 bg-surface-gray-2 p-1.5 text-ink-gray-6">
          <span :class="[type.icon, 'block size-4']" aria-hidden="true" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-base-medium text-ink-gray-8">{{ type.label }}</span>
          <span class="mt-0.5 block text-p-sm text-ink-gray-5">{{ type.description }}</span>
        </span>
        <span class="lucide-chevron-right mt-1 size-4 text-ink-gray-4" aria-hidden="true" />
      </button>
    </div>
  </Dialog>
</template>
