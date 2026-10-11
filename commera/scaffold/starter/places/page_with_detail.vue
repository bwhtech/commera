<script>
export const plugin = { label: '$label' }
</script>

<script setup>
import { Button } from 'frappe-ui'
import { EmptyState, usePlugin } from '@commera/admin'

const { navigate } = usePlugin()
</script>

<template>
  <EmptyState
    title="$label"
    description="Build this list in commera/$folder/index.vue. Open a record with navigate('$name/<id>')."
  />
  <Button class="mt-3" label="Open an example record" @click="navigate('$name/EXAMPLE-0001')" />
</template>
