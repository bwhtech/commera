<script setup>
import { usePage } from '@commera/admin'

const props = defineProps({ id: String })

usePage().setBreadcrumbs(() => [{ label: '$label', to: '$name' }, { label: props.id }])
</script>

<template>
  <p class="text-p-sm text-ink-gray-6">Build the view of {{ id }} in commera/$folder/[...id].vue.</p>
</template>
