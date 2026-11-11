export async function uploadTranslationImage(upload, file, key, field, apply) {
  const originalField = { ...field }
  const uploaded = await upload(file, { private: false })
  apply(key, originalField, uploaded.file_url)
}
