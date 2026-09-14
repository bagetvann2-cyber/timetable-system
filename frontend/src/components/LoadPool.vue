<script setup>
import { useScheduleStore, LESSON_TYPE_LABELS } from '../stores/schedule'

const store = useScheduleStore()

const typeColors = {
  lecture: 'bg-blue-100 text-blue-800',
  practice: 'bg-green-100 text-green-800',
  lab: 'bg-amber-100 text-amber-800',
}

function onDragStart(event, load) {
  store.startDrag(load.id)
  event.dataTransfer.effectAllowed = 'move'
}
function onDragEnd() {
  store.endDrag()
}
</script>

<template>
  <div class="w-72 shrink-0 border-r border-gray-200 overflow-y-auto p-3 space-y-2 bg-gray-50">
    <h2 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
      Нераспределённая нагрузка
    </h2>
    <p v-if="store.poolLoads.length === 0" class="text-sm text-gray-400 italic">
      Вся нагрузка расставлена
    </p>
    <div
      v-for="loadItem in store.poolLoads"
      :key="loadItem.id"
      draggable="true"
      @dragstart="onDragStart($event, loadItem)"
      @dragend="onDragEnd"
      class="cursor-grab active:cursor-grabbing rounded-lg border border-gray-200 bg-white p-3 shadow-sm hover:shadow transition-shadow"
    >
      <div class="flex items-center justify-between gap-2 mb-1">
        <span class="font-medium text-gray-900 text-sm">
          {{ store.subjectById(loadItem.subject_id)?.name }}
        </span>
        <span
          class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
          :class="typeColors[loadItem.lesson_type]"
        >
          {{ LESSON_TYPE_LABELS[loadItem.lesson_type] }}
        </span>
      </div>
      <div class="text-xs text-gray-500">
        {{ store.teacherById(loadItem.teacher_id)?.full_name }}
      </div>
      <div class="text-xs text-gray-500">
        {{ store.groupCodes(loadItem.group_ids) }} · {{ loadItem.students_total }} студ.
      </div>
      <div class="text-xs text-gray-400 mt-1">
        осталось {{ store.remaining(loadItem) }} из {{ loadItem.total_hours_per_week }}
      </div>
    </div>
  </div>
</template>
