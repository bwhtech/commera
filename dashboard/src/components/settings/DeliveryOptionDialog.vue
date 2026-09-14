<script setup>
/**
 * Creating or editing one delivery option.
 *
 * Every field below the title is the server's description of the doctype, rendered by the
 * same meta-driven rows as the carrier keys and the advanced tab — so a docfield added to
 * the shipping service reaches this form without a line changing here.
 */
import { computed, reactive, ref, useId, watch } from 'vue'
import { Button, Dialog, FormControl, SettingsRow, toast } from 'frappe-ui'
import SettingsFieldRows from './SettingsFieldRows.vue'

const props = defineProps({
  // Null while creating; the row being edited otherwise.
  option: { type: Object, default: null },
  groups: { type: Array, default: () => [] },
  // Set only where the server offers a picker for this doctype's Link fields. Without one a
  // Link stays a plain box rather than a combobox that can never fill itself.
  linkOptionsPath: { type: String, default: '' },
  submit: { type: Function, required: true },
})

const open = defineModel('open', { type: Boolean, required: true })

// The submit button sits outside the form, so `form` is what makes the browser run each
// field's `required` check.
const formId = useId()

const title = ref('')
const values = reactive({})
const saving = ref(false)

const isEdit = computed(() => Boolean(props.option))

// The title is what an order stores against its shipment, so renaming it after the fact
// would rewrite history the shopper already agreed to. It is set once, then read.
const editableGroups = computed(() =>
  props.groups
    .map((group) => ({
      ...group,
      fields: group.fields.filter((field) => field.fieldname !== 'title'),
    }))
    .filter((group) => group.fields.length),
)

// Reset on open rather than on mount: the dialog is kept alive between edits, so the
// second row opened would otherwise still hold the first row's answers.
watch(open, (isOpen) => {
  if (!isOpen) return

  title.value = props.option?.title ?? ''
  for (const key of Object.keys(values)) delete values[key]
  for (const group of props.groups) {
    for (const field of group.fields) {
      if (field.fieldname === 'title') continue
      // An existing row carries its own stored answer; `field.value` is the doctype's
      // default, which is what a new option should start from.
      values[field.fieldname] = props.option
        ? (props.option[field.fieldname] ?? '')
        : (field.value ?? '')
    }
  }
})

async function save() {
  saving.value = true
  try {
    // The title is only sent while creating — the server treats it as read-only after,
    // and sending it back would invite a refusal on an otherwise valid edit.
    const payload = isEdit.value ? { ...values } : { ...values, title: title.value.trim() }
    const saved = await props.submit(payload)
    if (!saved) return

    open.value = false
    toast.success(isEdit.value ? 'Delivery option saved' : 'Delivery option added')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:open="open"
    size="2xl"
    :title="isEdit ? 'Edit delivery option' : 'Add a delivery option'"
  >
    <template #default>
      <form :id="formId" @submit.prevent="save">
        <div class="divide-y divide-outline-gray-1">
          <SettingsRow
            v-if="isEdit"
            title="Name at checkout"
            description="Orders are stored against this name, so it cannot be changed."
          >
            <p class="w-72 text-base text-ink-gray-7">{{ option.title }}</p>
          </SettingsRow>

          <div v-else class="py-3.5">
            <FormControl
              v-model="title"
              label="Name at checkout"
              required
              placeholder="Standard delivery"
              description="What shoppers read beside the price. It cannot be changed later."
            />
          </div>

          <SettingsFieldRows
            :groups="editableGroups"
            :values="values"
            :link-options-path="linkOptionsPath"
            @update="(fieldname, value) => (values[fieldname] = value)"
          />
        </div>

        <!-- Left to the panel, which owns the stores: the dialog stays a plain form, and the
             slot can still fill one of its answers, e.g. a rate created on the spot. -->
        <slot name="after-fields" :set-value="(fieldname, value) => (values[fieldname] = value)" />
      </form>
    </template>

    <template #actions>
      <Button
        class="w-full"
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :label="isEdit ? 'Save' : 'Add'"
      />
    </template>
  </Dialog>
</template>
