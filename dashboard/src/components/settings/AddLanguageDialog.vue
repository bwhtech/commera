<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog, FormControl } from 'frappe-ui'
import { useLanguages } from '../../data/language'

const open = defineModel('open', { type: Boolean, default: false })
const props = defineProps({
  // Codes already on the storefront, which the picker leaves out.
  added: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['add'])

// Every enabled Frappe language, read when the dialog first opens.
const enabledLanguages = useLanguages()
const code = ref('')
const publish = ref(false)

const options = computed(() =>
  (enabledLanguages.data?.options ?? [])
    .filter((option) => !props.added.includes(option.value))
    .map(({ value, label, description }) => ({ value, label: description ? `${description} · ${label}` : label })),
)

watch(open, async (isOpen) => {
  if (!isOpen) return
  publish.value = false
  code.value = ''
  if (!enabledLanguages.data) await enabledLanguages.fetch()
  code.value = options.value[0]?.value ?? ''
})
</script>

<template>
  <Dialog v-model:open="open" :title="__('Add a language')">
    <template #default>
      <div class="space-y-4">
        <FormControl
          v-model="code"
          type="select"
          :label="__('Language')"
          :options="options"
          :disabled="enabledLanguages.loading"
        />
        <FormControl v-model="publish" type="checkbox" :label="__('Publish now')" />
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="open = false" />
        <Button
          variant="solid"
          theme="gray"
          :label="__('Add language')"
          :disabled="!code"
          :loading="saving"
          @click="emit('add', { code, publish })"
        />
      </div>
    </template>
  </Dialog>
</template>
