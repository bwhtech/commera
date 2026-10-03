import { ref } from 'vue'
import { toast } from 'frappe-ui'

// Frappe stores checks as 1/0 and numbers as numbers, while an input hands back a string or a
// boolean, so two values are the same when they would be stored the same.
function normalize(value) {
  if (value === true) return '1'
  if (value === false) return '0'
  return String(value ?? '')
}

/**
 * A settings panel that saves itself: there is no Save button, so every control writes its own
 * field the moment it settles.
 *
 * What is in the boxes is kept next to what the server last said was stored, because a write is
 * the only truth here — a refused one must not leave a box showing what the server refused, and a
 * value the controller rewrote on save wins over what was typed. Only the one field that changed
 * is ever submitted, so a blank secret means "keep the stored one" rather than "wipe it", and one
 * control's save never rewrites a field the owner never touched.
 */
// `params` rides along on every write, for an endpoint that serves more than one panel: a
// submit's own params replace the action's, so they cannot be set once on the action.
export function useSettingsAutosave(save, { params = {} } = {}) {
  const values = ref({})
  const stored = ref({})

  // Every control in the panel commits through the one `save` action, and a `useCall` is one
  // request at a time: VueUse's fetch aborts the in-flight request at the top of the next
  // `execute()`, and `data`/`error` are a single ref pair per instance — so two overlapping
  // commits abort each other and each `await` resolves reading the other's answer (frappe-ui
  // #991; its own fix, `useIsolatedCall`, is internal and exported from no entry point). They
  // overlap in one ordinary gesture: a text box commits on blur, and the control that took the
  // focus commits on its own mouseup ~50ms later. Chaining every commit onto one promise gives
  // each its own uncontested request, and last-write-wins ordering on the server for free. The
  // chain is carried forward with its rejection swallowed, so a commit that throws cannot wedge
  // the queue for the rest of the session — the caller still sees its own rejection.
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
  }

  // `afterSave` is for panels whose stored truth is wider than the save's answer — an analytics
  // secret that only stops reading as missing once the settings are re-read.
  async function commit(fieldname, value, label, afterSave) {
    if (normalize(value) === normalize(stored.value[fieldname])) return

    values.value[fieldname] = value

    return enqueue(async () => {
      const saved = await save.submit({ ...params, [fieldname]: value })
      // The refusal is read off the shared action, which only answers for this commit because
      // nothing else is in flight. Only the refused box rolls back: replacing the whole map
      // would wipe what the owner is typing into another field.
      if (save.error) {
        values.value[fieldname] = stored.value[fieldname]
        return
      }

      if (afterSave) await afterSave(saved)
      else adopt(saved)

      toast.success(`${label} saved`)
    })
  }

  return { values, stored, adopt, set, commit }
}
