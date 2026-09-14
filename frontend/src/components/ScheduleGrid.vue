<script setup>
import { ref, computed } from 'vue'
import { useScheduleStore, DAYS, LESSON_TYPE_LABELS } from '../stores/schedule'

const store = useScheduleStore()
const emit = defineEmits(['drop-request'])

const activeDragKey = ref(null)
const pendingKeys = new Set()

function cellKey(day, slotId) {
  return `${day}-${slotId}`
}

// Precomputed once per render instead of calling store.itemAt() repeatedly
// from the template for every cell.
const grid = computed(() =>
  store.timeSlots.map((slot) => ({
    slot,
    cells: DAYS.map((day) => ({
      day,
      item: store.itemAt(day.value, slot.id),
    })),
  })),
)

function onCellHover(day, slotId) {
  if (!store.dragging) return
  const key = cellKey(day, slotId)
  activeDragKey.value = key
  if (store.cellCache.has(key) || pendingKeys.has(key)) return
  pendingKeys.add(key)
  store
    .validateCell(store.dragging.loadId, store.dragging.itemId, day, slotId)
    .finally(() => pendingKeys.delete(key))
}

function onCellLeave(day, slotId) {
  if (activeDragKey.value === cellKey(day, slotId)) activeDragKey.value = null
}

function cellStatus(day, slotId) {
  const result = store.cellCache.get(cellKey(day, slotId))
  if (!result) return 'pending'
  if (!result.is_valid) return 'error'
  if (result.warnings.length > 0) return 'warn'
  return 'ok'
}

function cellMessages(day, slotId) {
  const result = store.cellCache.get(cellKey(day, slotId))
  if (!result) return []
  return [...result.errors, ...result.warnings]
}

function onDrop(day, slotId) {
  if (!store.dragging) return
  const status = cellStatus(day, slotId)
  if (status === 'error' || status === 'pending') return
  emit('drop-request', {
    loadId: store.dragging.loadId,
    itemId: store.dragging.itemId,
    day,
    slotId,
  })
  activeDragKey.value = null
}

function onItemDragStart(event, item) {
  store.startDrag(item.academic_load_id, item.id)
  event.dataTransfer.effectAllowed = 'move'
}
function onItemDragEnd() {
  store.endDrag()
  activeDragKey.value = null
}

const borderClasses = {
  pending: 'border-2 border-dashed border-gray-300',
  ok: 'border-2 border-green-500 bg-green-50',
  warn: 'border-2 border-amber-500 bg-amber-50',
  error: 'border-2 border-red-500 bg-red-50',
}

const typeColors = {
  lecture: 'bg-blue-100 text-blue-800',
  practice: 'bg-green-100 text-green-800',
  lab: 'bg-amber-100 text-amber-800',
}

function itemSubtitle(item) {
  const load = store.loadById(item.academic_load_id)
  if (!load) return ''
  if (store.viewMode === 'teacher') return store.groupCodes(load.group_ids)
  return store.teacherById(load.teacher_id)?.full_name ?? ''
}
</script>

<template>
  <div class="flex-1 overflow-auto p-3">
    <table class="w-full border-collapse table-fixed">
      <thead>
        <tr>
          <th
            class="w-24 text-left text-xs font-semibold text-gray-500 uppercase p-2 border-b border-gray-200"
          >
            Пара
          </th>
          <th
            v-for="day in DAYS"
            :key="day.value"
            class="text-xs font-semibold text-gray-500 uppercase p-2 border-b border-gray-200 text-center"
          >
            {{ day.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in grid" :key="row.slot.id">
          <td class="p-2 text-xs text-gray-500 border-b border-gray-100 align-top">
            {{ row.slot.slot_number }} пара<br />{{ row.slot.start_time }}–{{ row.slot.end_time }}
          </td>
          <td
            v-for="cell in row.cells"
            :key="cell.day.value"
            class="p-1 border-b border-gray-100 align-top relative"
            @dragover.prevent="onCellHover(cell.day.value, row.slot.id)"
            @dragleave="onCellLeave(cell.day.value, row.slot.id)"
            @drop="onDrop(cell.day.value, row.slot.id)"
          >
            <div
              class="h-16 rounded-md transition-colors"
              :class="
                store.dragging && activeDragKey === cellKey(cell.day.value, row.slot.id)
                  ? borderClasses[cellStatus(cell.day.value, row.slot.id)]
                  : 'border-2 border-transparent'
              "
            >
              <div
                v-if="cell.item"
                draggable="true"
                @dragstart="onItemDragStart($event, cell.item)"
                @dragend="onItemDragEnd"
                class="h-full rounded-md border border-gray-200 bg-white p-1.5 text-xs relative cursor-grab active:cursor-grabbing shadow-sm overflow-hidden"
              >
                <button
                  class="absolute top-0 right-0.5 text-gray-400 hover:text-red-600 leading-none px-1 text-sm"
                  @click="store.unassign(cell.item.id)"
                >
                  ×
                </button>
                <div class="font-medium text-gray-900 truncate pr-3">
                  {{ store.subjectById(store.loadById(cell.item.academic_load_id)?.subject_id)?.name }}
                </div>
                <div class="flex items-center gap-1 mt-0.5">
                  <span
                    class="text-[10px] px-1 rounded font-medium"
                    :class="typeColors[store.loadById(cell.item.academic_load_id)?.lesson_type]"
                  >
                    {{ LESSON_TYPE_LABELS[store.loadById(cell.item.academic_load_id)?.lesson_type] }}
                  </span>
                  <span class="text-gray-400 truncate">{{ store.roomById(cell.item.room_id)?.number }}</span>
                </div>
                <div class="text-gray-500 truncate">{{ itemSubtitle(cell.item) }}</div>
              </div>
            </div>
            <div
              v-if="
                activeDragKey === cellKey(cell.day.value, row.slot.id) &&
                cellMessages(cell.day.value, row.slot.id).length > 0
              "
              class="absolute z-10 top-full left-0 mt-1 w-56 rounded-md bg-gray-900 text-white text-xs p-2 shadow-lg"
            >
              <div v-for="(msg, i) in cellMessages(cell.day.value, row.slot.id)" :key="i">
                {{ msg }}
              </div>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
