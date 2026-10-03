<script setup>
import { ref } from 'vue'
import { Badge, Button, Dialog, FormControl, toast as frappeToast } from 'frappe-ui'
import { useExtension, useMethodAction, useMethodRead } from '@commera/admin'
import { statusTheme } from '../shared/status.js'

const { toast, setTitle, path, navigate } = useExtension()
setTitle('Printful')

const syncs = useMethodRead('print2commera.api.get_sync_history')
const startSync = useMethodAction('print2commera.api.start_sync', {
  onSuccess: (data) => {
    toast.success(data.message)
    syncs.reload()
  },
})

const clearing = ref(false)
const confirmation = ref('')
</script>

<template>
  <div class="space-y-4" data-printful-page>
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-ink-gray-9">Printful</h1>
      <div class="flex gap-2">
        <Button label="Clear stuck sync" @click="clearing = true" />
        <Button variant="solid" label="Sync now" :loading="startSync.loading" @click="startSync.submit()" />
      </div>
    </div>

    <p class="text-sm text-ink-gray-6">Sub-path: {{ path || '(root)' }}</p>
    <div class="flex gap-2">
      <Button label="Open syncs sub-page" @click="navigate('syncs')" />
      <!-- frappe-ui imported directly, not through useExtension(): only shows
           because the extension shares the host's frappe-ui instance. -->
      <Button label="Direct toast" @click="frappeToast.success('Toast via frappe-ui import')" />
    </div>

    <section class="rounded-5 border border-outline-gray-2">
      <div
        v-for="run in syncs.data ?? []"
        :key="run.id"
        class="flex items-center justify-between border-b border-outline-gray-2 px-4 py-3 text-sm"
      >
        <span>{{ run.started }}</span>
        <Badge :label="run.status" :theme="statusTheme(run.status)" />
      </div>
    </section>

    <Dialog v-model:open="clearing" title="Clear stuck sync" size="sm">
      <template #default>
        <p class="mb-3 text-sm text-ink-gray-7">Type CLEAR to mark the running sync as abandoned.</p>
        <FormControl v-model="confirmation" placeholder="CLEAR" />
      </template>
      <template #actions>
        <Button
          variant="solid"
          theme="red"
          label="Clear"
          :disabled="confirmation !== 'CLEAR'"
          @click="(clearing = false), toast.success('Stuck sync cleared')"
        />
      </template>
    </Dialog>
  </div>
</template>
