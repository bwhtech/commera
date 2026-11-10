<script setup>
import { Button, Popover, TabButtons } from 'frappe-ui'
import { storefrontLanguageOptions } from '../../data/boot'

defineProps({
  state: { type: Object, required: true },
  devices: { type: Boolean, default: true },
})

const DEVICES = [
  { label: 'Desktop', value: 'desktop', icon: 'lucide-monitor' },
  { label: 'Mobile', value: 'mobile', icon: 'lucide-smartphone' },
  { label: 'Desktop and mobile', value: 'both', icon: 'lucide-columns-2' },
]
</script>

<template>
  <Popover side="top" align="center" :offset="8">
    <template #trigger="{ open }">
      <Button
        :variant="open ? 'subtle' : 'ghost'"
        icon="lucide-ellipsis"
        aria-label="More preview options"
        :aria-expanded="open"
      />
    </template>
    <template #default>
      <div class="flex w-36 flex-col gap-1.5 p-1" data-preview-options>
        <TabButtons v-if="devices" v-model="state.device" :options="DEVICES" fluid aria-label="Device" />
        <TabButtons
          v-if="storefrontLanguageOptions.length > 1"
          v-model="state.language"
          :options="storefrontLanguageOptions"
          fluid
          aria-label="Preview language"
        />
      </div>
    </template>
  </Popover>
</template>
