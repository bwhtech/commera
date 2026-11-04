const FIELDTYPES = {
  text: 'Data',
  textarea: 'Small Text',
  url: 'Data',
  image: 'Attach Image',
  number: 'Float',
  checkbox: 'Check',
  select: 'Select',
  collection: 'Collection',
  products: 'Products',
}

export function readableName(code) {
  return code.replace(/[_-]/g, ' ').replace(/^\w/, (letter) => letter.toUpperCase())
}

export function sectionSettingToField(setting) {
  const fieldtype = FIELDTYPES[setting.type]
  if (!fieldtype) throw new Error(`Unknown section setting type: ${setting.type}`)

  return {
    fieldname: setting.id,
    label: setting.label ?? setting.id,
    fieldtype,
    options: setting.type === 'select' ? (setting.options ?? []).join('\n') : undefined,
    option_labels:
      setting.type === 'select'
        ? Object.fromEntries((setting.options ?? []).map((option) => [option, readableName(option)]))
        : undefined,
    default: setting.default,
  }
}
