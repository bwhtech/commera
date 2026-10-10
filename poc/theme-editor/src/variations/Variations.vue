<script setup>
import { Button } from 'frappe-ui'
import { useRouter } from 'vue-router'

const router = useRouter()
const variants = [
  { key: 'a', title: 'A · One screen, one tool', rule: 'Theme is for your store pages. Pages is for pages you add, and they open in Builder.' },
  { key: 'b', title: 'B · Every page in one list', rule: 'All pages are in Pages with one Edit button; the page decides which editor opens. Theme is only the look.' },
  { key: 'c', title: 'C · Text pages vs designed pages', rule: 'Write text pages right here; design campaign pages in Builder. You choose when you create one.' },
]
</script>

<template>
  <div class="mx-auto max-w-3xl px-6 py-10">
    <h1 class="text-2xl font-semibold text-ink-gray-9">Pages and Builder: three simpler variations</h1>
    <p class="mt-1 text-base text-ink-gray-6">Each one rests on a single rule a new merchant can learn. The theme editor itself is unchanged, and none of them put Builder inside it.</p>
    <div class="mt-6 space-y-3">
      <div v-for="variant in variants" :key="variant.key" class="flex items-center gap-4 rounded-lg border border-outline-gray-2 p-4">
        <div class="min-w-0 flex-1">
          <p class="text-lg font-semibold text-ink-gray-9">{{ variant.title }}</p>
          <p class="text-base text-ink-gray-6">{{ variant.rule }}</p>
        </div>
        <Button label="Open" icon-right="lucide-arrow-right" @click="router.push(`/variations/${variant.key}`)" />
      </div>
    </div>
  </div>
</template>
