# Commera plugins for $app_name

Everything in this folder is built into the Commera dashboard at `/commera`. The folder an `index.vue`
sits in decides where it shows. While you work, run `yarn dev` in
`apps/commera/dashboard` and open `/commera` on its port (8080): a saved file updates in place. For production,
build with `bench build --app $app_name`.

| Folder | What it adds |
| --- | --- |
| `pages/<name>/` | A page at `/commera/plugins/$app_name/<name>`, with a row in the sidebar |
| `order/cards/<name>/`, `product/cards/<name>/`, `customer/cards/<name>/` | A card on that record's page |
| `order/actions/<name>/`, `product/actions/<name>/`, `customer/actions/<name>/` | A row in that record page's More actions menu |
| `settings/` | The app's tab in Settings |

`<name>` is 1 to 40 lowercase letters, digits and hyphens. Empty folders are placeholders: delete the ones
you don't use.

## Rules

- Each `index.vue` starts with a plain `<script>` holding one `export const plugin = { … }`. Its values
  must be literals: no imports, variables, function calls or spreads.
- Commera draws the frame: the page header, the card title, the dialog with its buttons, the settings
  heading. Fill only the content. Set the page header with `usePage()` and the dialog's button with
  `useAction()`; don't import `AppPageHeader`, `PageBody` or frappe-ui's `Dialog`.
- `condition` and `method` are dotted paths that start with `$app_name.`. A page or settings `condition`
  takes no arguments; a card or action `condition` gets `(doctype, name)` and returns a bool.
- `icon` is optional; without it the entry uses the app's icon (`commera/plugin-icon.svg`). It is a name from
  Commera's list (`commera/sdk/plugin_icons.json`), such as `gift` or `star`.
- Read and write data with `useMethodRead` and `useMethodAction` from `@commera/admin`, pointed at a
  whitelisted method in `$app_name/api.py`. frappe-ui's `createResource`, `useCall`, `useList`, `useDoc`
  and the like call Frappe's v1 API, which the dashboard reads as null, so they fail the build.
- Import shared code only from `vue`, `frappe-ui`, `frappe-ui/list`, `frappe-ui/charts` and `@commera/admin`;
  the dashboard supplies them. Any other `frappe-ui/` subpath fails the build.
- No `<style>` blocks: use the frappe-ui classes the dashboard already ships.
- Folders that are not in the table are ignored. Put shared components and helpers in any other folder,
  for example `commera/shared/`, and import them with a relative path.

## Starters

`bench commera init` wrote a starter page that calls `$app_name.api.get_summary` in `$app_name/api.py`.
The starters below put their whitelisted methods in that same file. When you replace the starter page
`pages/$page_name/index.vue`, delete `get_summary` from `$app_name/api.py` too: nothing else calls it.

### A page: `pages/<name>/index.vue`

```vue
<script>
export const plugin = { label: 'Jobs', icon: 'list-checks', order: 1 }
</script>

<script setup>
import { computed } from 'vue'
import { EmptyState, useMethodRead, usePage } from '@commera/admin'

const jobsRequest = useMethodRead('$app_name.api.get_jobs')
const jobs = computed(() => jobsRequest.data ?? [])

usePage().setActions([{ label: 'Refresh', icon: 'refresh-cw', onClick: () => jobsRequest.reload() }])
</script>

<template>
  <EmptyState v-if="!jobsRequest.loading && !jobs.length" title="No jobs yet" />
  <p v-for="job in jobs" :key="job.name" class="text-base text-ink-gray-8">{{ job.title }}</p>
</template>
```

### A card: `order/cards/<name>/index.vue`

```vue
<script>
export const plugin = { label: 'Jobs', condition: '$app_name.conditions.order_has_jobs' }
</script>

<script setup>
import { watch } from 'vue'
import { useCard, usePlugin, useMethodRead } from '@commera/admin'

const { record } = usePlugin()
const card = useCard()

const countRequest = useMethodRead('$app_name.api.get_order_job_count', {
  params: () => ({ sales_order: record.value.name }),
})

watch(() => countRequest.data, (count) => card.setHidden(count === 0))
</script>

<template>
  <p class="text-base text-ink-gray-8 tabular-nums">{{ countRequest.data ?? 0 }} jobs</p>
</template>
```

### An action with a dialog: `order/actions/<name>/index.vue`

```vue
<script>
export const plugin = { label: 'Add a note', icon: 'message-square' }
</script>

<script setup>
import { ref } from 'vue'
import { FormControl } from 'frappe-ui'
import { useAction, usePlugin, useMethodAction } from '@commera/admin'

const { record } = usePlugin()
const action = useAction()
const note = ref('')
const addNote = useMethodAction('$app_name.api.add_order_note')

action.setPrimary({ label: 'Add note', disabled: () => !note.value.trim() })

action.onSubmit(async () => {
  await addNote.submit({ sales_order: record.value.name, note: note.value })
  if (addNote.error) throw addNote.error
  return { reload: true }
})
</script>

<template>
  <FormControl v-model="note" type="textarea" label="Note" />
</template>
```

### An action that runs a method: `order/actions/<name>/index.vue`

No template: Commera asks `confirm`, then calls the whitelisted `method` with the record's `name`. A string it
returns is shown as a toast.

```vue
<script>
export const plugin = {
  label: 'Resend to printer',
  icon: 'printer',
  method: '$app_name.api.resend_order',
  confirm: "Send this order's jobs again?",
}
</script>
```

### Settings from a Single: `settings/index.vue`

Commera draws every field of the Single as a row that saves itself. A `reqd` field shows a `*` and cannot be
cleared, but each row saves while other required rows are still blank, so your `validate` must allow that.
Check the required values in your own code before you use them.

```vue
<script>
export const plugin = { label: 'Jobs', icon: 'settings', doctype: '$label Settings' }
</script>
```

### Settings with your own form: `settings/index.vue`

```vue
<script>
export const plugin = { label: 'Jobs', icon: 'settings' }
</script>

<script setup>
import { ref } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import { usePlugin, useMethodAction } from '@commera/admin'

const { toast } = usePlugin()
const printerUrl = ref('')
const saveSettings = useMethodAction('$app_name.api.save_printer_url')

async function save() {
  await saveSettings.submit({ printer_url: printerUrl.value })
  if (!saveSettings.error) toast.success('Saved')
}
</script>

<template>
  <FormControl v-model="printerUrl" label="Printer URL" />
  <Button class="mt-3" label="Save" variant="solid" :loading="saveSettings.loading" @click="save" />
</template>
```
