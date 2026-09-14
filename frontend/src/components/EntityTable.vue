<script setup>
import { reactive, ref } from 'vue'
import { useScheduleStore } from '../stores/schedule'

// Generic create/edit/delete table for the simple, flat reference entities
// (buildings, rooms, teachers, groups, subjects, time slots). Academic loads
// have their own editor (LoadEditor.vue) because of the group multi-select.
const props = defineProps({
  entity: { type: String, required: true }, // key into ENTITY_PATHS in the store
  title: { type: String, required: true },
  items: { type: Array, required: true },
  // [{ key, label, type: 'text'|'number'|'checkbox'|'select', options?: () => [{value,label}] }]
  fields: { type: Array, required: true },
})

const store = useScheduleStore()
const editingId = ref(null) // null = "creating new"
const saving = ref(false)

function emptyForm() {
  const obj = {}
  for (const f of props.fields) {
    if (f.type === 'checkbox') obj[f.key] = false
    else if (f.type === 'number') obj[f.key] = 0
    else if (f.type === 'select') obj[f.key] = f.options()[0]?.value ?? null
    else obj[f.key] = ''
  }
  return obj
}
const form = reactive(emptyForm())

function startEdit(item) {
  editingId.value = item.id
  for (const f of props.fields) form[f.key] = item[f.key]
}
function cancelEdit() {
  editingId.value = null
  Object.assign(form, emptyForm())
}

async function submit() {
  saving.value = true
  try {
    const payload = {}
    for (const f of props.fields) payload[f.key] = form[f.key]
    if (editingId.value === null) {
      await store.createEntity(props.entity, payload)
    } else {
      await store.updateEntity(props.entity, editingId.value, payload)
    }
    cancelEdit()
  } catch {
    // store.error already holds the message; keep the form open so the
    // user can fix the values and retry.
  } finally {
    saving.value = false
  }
}

async function remove(item) {
  if (!confirm('Удалить? Связанные данные (нагрузка, пары в расписании) тоже будут удалены.')) return
  try {
    await store.deleteEntity(props.entity, item.id)
    if (editingId.value === item.id) cancelEdit()
  } catch {
    // store.error already set
  }
}

function displayValue(field, item) {
  if (field.type === 'checkbox') return item[field.key] ? 'да' : 'нет'
  if (field.type === 'select') {
    return field.options().find((o) => o.value === item[field.key])?.label ?? item[field.key]
  }
  return item[field.key]
}
</script>

<template>
  <div class="p-4">
    <h2 class="font-semibold text-gray-900 mb-3">{{ title }}</h2>

    <form
      class="flex flex-wrap items-end gap-3 mb-4 p-3 bg-gray-50 rounded-md border border-gray-200"
      @submit.prevent="submit"
    >
      <div v-for="f in fields" :key="f.key" class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">{{ f.label }}</label>
        <select
          v-if="f.type === 'select'"
          v-model.number="form[f.key]"
          class="border border-gray-300 rounded px-2 py-1 text-sm"
          required
        >
          <option v-for="o in f.options()" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <input
          v-else-if="f.type === 'checkbox'"
          v-model="form[f.key]"
          type="checkbox"
          class="mt-2"
        />
        <input
          v-else-if="f.type === 'number'"
          v-model.number="form[f.key]"
          type="number"
          class="border border-gray-300 rounded px-2 py-1 text-sm w-24"
          required
        />
        <input
          v-else
          v-model="form[f.key]"
          type="text"
          class="border border-gray-300 rounded px-2 py-1 text-sm w-36"
          required
        />
      </div>
      <div class="flex gap-2">
        <button
          type="submit"
          :disabled="saving"
          class="px-3 py-1.5 text-sm rounded bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {{ editingId === null ? 'Добавить' : 'Сохранить' }}
        </button>
        <button
          v-if="editingId !== null"
          type="button"
          class="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-800"
          @click="cancelEdit"
        >
          Отмена
        </button>
      </div>
    </form>

    <table class="w-full text-sm border-collapse">
      <thead>
        <tr class="text-left text-xs text-gray-500 uppercase">
          <th v-for="f in fields" :key="f.key" class="p-2 border-b border-gray-200">{{ f.label }}</th>
          <th class="p-2 border-b border-gray-200 w-24"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id" class="hover:bg-gray-50">
          <td v-for="f in fields" :key="f.key" class="p-2 border-b border-gray-100">
            {{ displayValue(f, item) }}
          </td>
          <td class="p-2 border-b border-gray-100 text-right whitespace-nowrap">
            <button class="text-gray-400 hover:text-gray-800 text-xs mr-2" @click="startEdit(item)">
              Изм.
            </button>
            <button class="text-gray-400 hover:text-red-600 text-xs" @click="remove(item)">
              Удал.
            </button>
          </td>
        </tr>
        <tr v-if="items.length === 0">
          <td :colspan="fields.length + 1" class="p-3 text-center text-gray-400 text-sm">Пусто</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
