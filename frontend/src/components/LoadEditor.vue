<script setup>
import { reactive, ref } from 'vue'
import { useScheduleStore, LESSON_TYPE_LABELS } from '../stores/schedule'

// Academic loads get their own editor (not EntityTable) because of the
// group multi-select and the subject/teacher/type dropdowns.
const store = useScheduleStore()
const editingId = ref(null) // null = "creating new"
const saving = ref(false)

function emptyForm() {
  return {
    subject_id: store.subjects[0]?.id ?? null,
    teacher_id: store.teachers[0]?.id ?? null,
    lesson_type: 'lecture',
    total_hours_per_week: 2,
    group_ids: [],
  }
}
const form = reactive(emptyForm())

function startEdit(loadItem) {
  editingId.value = loadItem.id
  form.subject_id = loadItem.subject_id
  form.teacher_id = loadItem.teacher_id
  form.lesson_type = loadItem.lesson_type
  form.total_hours_per_week = loadItem.total_hours_per_week
  form.group_ids = [...loadItem.group_ids]
}
function cancelEdit() {
  editingId.value = null
  Object.assign(form, emptyForm())
}

async function submit() {
  saving.value = true
  try {
    const payload = { ...form }
    if (editingId.value === null) {
      await store.createEntity('loads', payload)
    } else {
      await store.updateEntity('loads', editingId.value, payload)
    }
    cancelEdit()
  } catch {
    // store.error already holds the message; keep the form open so the
    // user can fix the values and retry.
  } finally {
    saving.value = false
  }
}

async function remove(loadItem) {
  if (!confirm('Удалить карточку нагрузки? Расставленные пары тоже будут удалены.')) return
  try {
    await store.deleteEntity('loads', loadItem.id)
    if (editingId.value === loadItem.id) cancelEdit()
  } catch {
    // store.error already set
  }
}
</script>

<template>
  <div class="p-4">
    <h2 class="font-semibold text-gray-900 mb-3">Нагрузка</h2>

    <form
      class="flex flex-wrap items-start gap-3 mb-4 p-3 bg-gray-50 rounded-md border border-gray-200"
      @submit.prevent="submit"
    >
      <div class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">Предмет</label>
        <select
          v-model.number="form.subject_id"
          class="border border-gray-300 rounded px-2 py-1 text-sm"
          required
        >
          <option v-for="s in store.subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">Преподаватель</label>
        <select
          v-model.number="form.teacher_id"
          class="border border-gray-300 rounded px-2 py-1 text-sm"
          required
        >
          <option v-for="t in store.teachers" :key="t.id" :value="t.id">{{ t.full_name }}</option>
        </select>
      </div>
      <div class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">Тип</label>
        <select v-model="form.lesson_type" class="border border-gray-300 rounded px-2 py-1 text-sm">
          <option v-for="(label, key) in LESSON_TYPE_LABELS" :key="key" :value="key">
            {{ label }}
          </option>
        </select>
      </div>
      <div class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">Часов в неделю</label>
        <input
          v-model.number="form.total_hours_per_week"
          type="number"
          min="1"
          class="border border-gray-300 rounded px-2 py-1 text-sm w-24"
          required
        />
      </div>
      <div class="flex flex-col">
        <label class="text-xs text-gray-500 mb-0.5">Группы</label>
        <div class="flex flex-wrap gap-x-3 gap-y-1 border border-gray-300 rounded px-2 py-1.5 bg-white max-w-xs">
          <label v-for="g in store.groups" :key="g.id" class="flex items-center gap-1 text-sm">
            <input v-model="form.group_ids" type="checkbox" :value="g.id" />
            {{ g.code }}
          </label>
        </div>
      </div>
      <div class="flex gap-2 pt-4">
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
          <th class="p-2 border-b border-gray-200">Предмет</th>
          <th class="p-2 border-b border-gray-200">Тип</th>
          <th class="p-2 border-b border-gray-200">Преподаватель</th>
          <th class="p-2 border-b border-gray-200">Группы</th>
          <th class="p-2 border-b border-gray-200">Часов</th>
          <th class="p-2 border-b border-gray-200 w-24"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="loadItem in store.loads" :key="loadItem.id" class="hover:bg-gray-50">
          <td class="p-2 border-b border-gray-100">{{ store.subjectById(loadItem.subject_id)?.name }}</td>
          <td class="p-2 border-b border-gray-100">{{ LESSON_TYPE_LABELS[loadItem.lesson_type] }}</td>
          <td class="p-2 border-b border-gray-100">
            {{ store.teacherById(loadItem.teacher_id)?.full_name }}
          </td>
          <td class="p-2 border-b border-gray-100">{{ store.groupCodes(loadItem.group_ids) }}</td>
          <td class="p-2 border-b border-gray-100">
            {{ store.remaining(loadItem) }} / {{ loadItem.total_hours_per_week }} ост.
          </td>
          <td class="p-2 border-b border-gray-100 text-right whitespace-nowrap">
            <button class="text-gray-400 hover:text-gray-800 text-xs mr-2" @click="startEdit(loadItem)">
              Изм.
            </button>
            <button class="text-gray-400 hover:text-red-600 text-xs" @click="remove(loadItem)">
              Удал.
            </button>
          </td>
        </tr>
        <tr v-if="store.loads.length === 0">
          <td colspan="6" class="p-3 text-center text-gray-400 text-sm">Пусто</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
