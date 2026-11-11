import { ref } from 'vue'
import { toast } from 'frappe-ui'
import { __ } from './translation'

// Frappe stores checks as 1/0 and numbers as numbers, while an input hands back a string or a
// boolean, so two values are the same when they would be stored the same.
function normalize(value) {
  if (value === true) return '1'
  if (value === false) return '0'
  return String(value ?? '')
}

// Extra params identify the record while each commit writes only its changed field.
export function useSettingsAutosave(save, { params = {}, preserveEdits = false } = {}) {
  const values = ref({})
  const stored = ref({})
  const revisions = {}
  const pending = {}

  // useCall shares one response and aborts overlapping requests, so each commit waits its turn.
  // A failed request must not wedge later writes.
  let queue = Promise.resolve()

  function enqueue(write) {
    const result = queue.then(write)
    queue = result.catch(() => {})
    return result
  }

  // Merged, not replaced: a panel adopts the fields it owns — a group, a section — one answer at
  // a time, and adopting one must not forget the rest.
  function adopt(record) {
    stored.value = { ...stored.value, ...record }
    values.value = { ...values.value, ...record }
  }

  // What is being typed, before it is worth writing.
  function set(fieldname, value) {
    values.value[fieldname] = value
    revisions[fieldname] = (revisions[fieldname] ?? 0) + 1
  }

  // `afterSave` is for panels whose stored truth is wider than the save's answer — an analytics
  // secret that only stops reading as missing once the settings are re-read.
  async function commit(fieldname, value, label, afterSave) {
    if (!pending[fieldname] && normalize(value) === normalize(stored.value[fieldname])) return

    set(fieldname, value)
    const revision = revisions[fieldname]
    pending[fieldname] = (pending[fieldname] ?? 0) + 1

    return enqueue(async () => {
      let saved
      try {
        saved = await save.submit({ ...params, [fieldname]: value })
      } catch {
        pending[fieldname] -= 1
        if (!preserveEdits || revisions[fieldname] === revision) {
          values.value[fieldname] = stored.value[fieldname]
        }
        return
      }

      pending[fieldname] -= 1
      if (preserveEdits) {
        const next = { ...values.value }
        for (const [field, savedValue] of Object.entries(saved)) {
          const unchanged = normalize(values.value[field]) === normalize(stored.value[field])
          const completed = field === fieldname && revisions[field] === revision
          if (completed || (field !== fieldname && unchanged && !pending[field])) next[field] = savedValue
        }
        stored.value = { ...stored.value, ...saved }
        values.value = next
      }
      if (afterSave) await afterSave(saved)
      else if (!preserveEdits) adopt(saved)

      toast.success(__('{0} saved', [label]))
    })
  }

  return { values, stored, adopt, set, commit }
}
