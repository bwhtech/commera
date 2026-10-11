<script setup>
import { computed, provide, ref, shallowRef, toValue, watch } from 'vue'
import { Button, Dialog, ErrorMessage } from 'frappe-ui'
import { ACTION_CONTEXT } from '../plugin-api/context'
import { errorMessage } from '../data/errors'
import PluginHost from './PluginHost.vue'

const props = defineProps({
  record: { type: Object, required: true },
})

const entry = defineModel('entry', { type: Object, default: null })
const emit = defineEmits(['reload'])

// Kept past close, so the title does not blank while the dialog animates out.
const shownEntry = shallowRef(null)
const primarySource = shallowRef(null)
const submitHandler = shallowRef(null)
const submitting = ref(false)
const failure = ref('')
const moduleFailed = ref(false)

watch(
  entry,
  (current) => {
    if (!current) return
    shownEntry.value = current
    primarySource.value = null
    submitHandler.value = null
    failure.value = ''
    moduleFailed.value = false
  },
  { immediate: true },
)

const open = computed({
  get: () => Boolean(entry.value),
  set: (isOpen) => !isOpen && (entry.value = null),
})

function finish(result) {
  entry.value = null
  if (result?.reload) emit('reload')
}

provide(ACTION_CONTEXT, {
  setPrimary: (options) => (primarySource.value = options),
  onSubmit: (handler) => (submitHandler.value = handler),
  close: finish,
})

const primary = computed(() => {
  const options = toValue(primarySource.value) ?? {}
  return {
    label: toValue(options.label) || shownEntry.value?.label,
    disabled: Boolean(toValue(options.disabled)),
    loading: Boolean(toValue(options.loading)),
  }
})

// A throw keeps the dialog open with the reason under the form; a resolve closes it.
async function submit() {
  if (!submitHandler.value) return finish()
  submitting.value = true
  failure.value = ''
  try {
    finish(await submitHandler.value())
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="shownEntry?.label" :dismissible="!submitting">
    <template #default>
      <PluginHost
        v-if="entry"
        :key="entry.key"
        :entry="entry"
        :record="props.record"
        @reload="emit('reload')"
        @failed="moduleFailed = true"
      />
      <ErrorMessage v-if="failure" class="mt-3" :message="failure" />
    </template>

    <template #actions>
      <!-- Stacked on a phone and side by side from sm up, the same footer RefundDialog uses. -->
      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button class="w-full sm:w-auto" label="Cancel" :disabled="submitting" @click="open = false" />
        <Button
          class="w-full sm:w-auto"
          variant="solid"
          theme="gray"
          :label="primary.label"
          :loading="submitting || primary.loading"
          :disabled="moduleFailed || primary.disabled || submitting"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>
