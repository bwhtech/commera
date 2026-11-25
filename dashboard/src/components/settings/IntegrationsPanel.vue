<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, SettingsBody, Skeleton, toast } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import EmptyState from '../EmptyState.vue'
import IntegrationCard from './IntegrationCard.vue'
import IntegrationConfig from './IntegrationConfig.vue'
import { __ } from '../../data/translation'

const props = defineProps({
  store: { type: Object, required: true },
  title: { type: String, required: true },
  // Opening the dialog should fetch; switching away and back should not.
  active: { type: Boolean, default: false },
})

// A model: the host panel has to know a takeover screen is open to give it a bounded height.
const configuring = defineModel('configuring', { type: String, default: null })
const current = computed(
  () => props.store.cards.value.find((card) => card.slug === configuring.value) ?? null,
)
const turningOn = ref(false)
watch(configuring, (slug) => !slug && (turningOn.value = false))

watch(() => props.active, (isActive) => isActive && props.store.loadOnce(), { immediate: true })

async function toggle(card, enabled) {
  if (enabled && card.missing?.length) {
    turningOn.value = true
    configuring.value = card.slug
    return
  }

  const saved = await props.store.save(card.slug, enabled, {})
  if (!saved) return

  if (saved.enabled) toast.success(__('{0} is on', [saved.label]))
  else toast.success(__('{0} is off', [saved.label]))
}

async function saveCurrent(values) {
  const enabled = turningOn.value || current.value.enabled
  const saved = await props.store.save(current.value.slug, enabled, values)
  if (!saved) return

  configuring.value = null
  if (turningOn.value) toast.success(__('{0} is on', [saved.label]))
  else toast.success(__('{0} saved', [saved.label]))
}
</script>

<template>
  <template v-if="!current">
    <SettingsPanelHeader :title="title">
      <template #actions>
        <Badge
          v-if="store.incomplete.value.length"
          :label="
            store.incomplete.value.length === 1
              ? __('1 needs keys')
              : __('{0} need keys', [store.incomplete.value.length])
          "
          theme="amber"
          variant="subtle"
        />
      </template>
    </SettingsPanelHeader>
    <SettingsBody v-scroll-fade>
      <!-- A refused read must not read as "this store has no providers". -->
      <div v-if="store.loadError.value" class="py-6 text-base text-ink-gray-5">
        {{ __('These could not be loaded.') }}
        <Button :label="__('Try again')" variant="ghost" @click="store.load()" />
      </div>
      <!-- Shaped like IntegrationCard's row so the list does not shift. First load only: a
           save keeps `cards` populated and must not blank the list under the switch. -->
      <div
        v-else-if="store.loading.value && !store.cards.value.length"
        class="divide-y divide-outline-gray-1"
        aria-hidden="true"
      >
        <div v-for="row in 3" :key="row" class="flex items-center gap-3 py-3">
          <Skeleton class="h-9 w-24 shrink-0 rounded-5" />
          <Skeleton class="h-4 w-32 rounded-4" />
          <Skeleton class="ms-auto h-4 w-8 shrink-0 rounded-full" />
        </div>
      </div>
      <!-- Nothing installed answers with an empty registry, not a refusal — without this
           the divider stack renders as a blank panel under the heading. -->
      <EmptyState
        v-else-if="!store.cards.value.length"
        compact
        icon="lucide-plug"
        :title="__('No integrations available')"
        :description="__('Install a payments or delivery app to see it here.')"
      />
      <div v-else class="divide-y divide-outline-gray-1">
        <IntegrationCard
          v-for="card in store.cards.value"
          :key="card.slug"
          :card="card"
          :busy="store.loading.value"
          @configure="configuring = $event"
          @toggle="toggle(card, $event)"
        />
      </div>
    </SettingsBody>
  </template>

  <IntegrationConfig
    v-else
    :card="current"
    :turning-on="turningOn"
    :saving="store.loading.value"
    @back="configuring = null"
    @save="saveCurrent"
  />
</template>
