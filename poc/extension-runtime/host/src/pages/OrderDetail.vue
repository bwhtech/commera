<script setup>
import { useRoute } from 'vue-router'
import { Badge } from 'frappe-ui'
import ExtensionSlot from '../components/ExtensionSlot.vue'

const route = useRoute()
const resource = { doctype: 'Sales Order', name: route.params.id }
</script>

<template>
  <div class="flex gap-6 p-8">
    <div class="min-w-0 flex-1">
      <h1 class="text-2xl font-semibold">{{ resource.name }}</h1>
      <Badge class="mt-2" label="Order Received" theme="blue" />
      <section class="mt-6 rounded-5 border border-outline-gray-2 p-4 text-sm">
        2 × Unisex Tee (Black, M) — host-rendered order lines
      </section>
    </div>
    <aside class="w-80 shrink-0">
      <ExtensionSlot target="admin.order-details.block" :resource="resource" />
    </aside>
  </div>
</template>
