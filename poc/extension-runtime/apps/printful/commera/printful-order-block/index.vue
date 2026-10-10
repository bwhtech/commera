<script setup>
import { Badge } from 'frappe-ui'
import { ExtensionCard, money, useExtension, useMethodRead } from '@commera/admin'
import { statusTheme } from '../shared/status.js'

const { resource } = useExtension()
const panel = useMethodRead('print2commera.api.get_order_panel', {
  params: { sales_order: resource.name },
})
</script>

<template>
  <ExtensionCard v-if="panel.data" title="Printful" data-printful-block>
    <template #actions>
      <Badge :label="panel.data.status" :theme="statusTheme(panel.data.status)" />
    </template>
    <p>Printful order {{ panel.data.printful_order_id }} for {{ resource.name }}</p>
    <p>Cost {{ money(panel.data.cost) }} · Retail {{ money(panel.data.retail) }}</p>
    <p class="font-semibold text-ink-gray-9">Margin {{ money(panel.data.retail - panel.data.cost) }}</p>
  </ExtensionCard>
</template>
