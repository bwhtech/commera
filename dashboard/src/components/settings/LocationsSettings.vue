<script setup>
/**
 * Where the storefront ships from. This shop sells out of one warehouse, so this is a statement of
 * fact rather than a list to manage — the warehouse itself is set up in the books.
 */
import { watch } from 'vue'
import { Badge, SettingsBody, SettingsHeader } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminRead } from '../../data/api'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const locations = useAdminRead('settings.get_locations', { immediate: false })

watch(
  () => props.active,
  (isActive) => isActive && !locations.isFinished && locations.reload(),
  { immediate: true },
)
</script>

<template>
  <SettingsHeader title="Locations" description="The warehouse online orders are fulfilled from." />

  <SettingsBody>
    <!-- A warehouse row is a name, a sub-line and a badge — the same two-lines-and-a-control
         shape a settings row has, so it wears the same placeholder. -->
    <SettingsSkeleton v-if="locations.loading && !locations.data" :rows="2" />

    <EmptyState
      v-else-if="!locations.data?.length"
      compact
      icon="lucide-warehouse"
      title="No ecommerce warehouse is set yet"
      description="Orders have nothing to reserve stock against. Set one under Advanced → Ecommerce Warehouse."
    />

    <div v-else class="divide-y divide-outline-gray-1">
      <div
        v-for="location in locations.data"
        :key="location.name"
        class="flex items-center justify-between gap-3 py-3"
      >
        <div class="min-w-0">
          <p class="truncate text-base text-ink-gray-8">{{ location.warehouse_name }}</p>
          <p class="mt-1 truncate text-sm text-ink-gray-5">
            {{ location.name }}<span v-if="location.company"> · {{ location.company }}</span>
          </p>
        </div>
        <Badge
          :label="location.disabled ? 'Disabled' : 'Fulfils online orders'"
          :theme="location.disabled ? 'amber' : 'green'"
          variant="subtle"
        />
      </div>
    </div>
  </SettingsBody>
</template>
