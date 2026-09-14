<script setup>
import { onMounted, ref } from 'vue'
import { useScheduleStore } from './stores/schedule'
import LoadPool from './components/LoadPool.vue'
import ScheduleGrid from './components/ScheduleGrid.vue'
import RoomPickerModal from './components/RoomPickerModal.vue'

const store = useScheduleStore()
const modalRequest = ref(null) // { loadId, itemId, day, slotId } | null

onMounted(() => {
  store.load().catch(() => {})
})

function onDropRequest(request) {
  modalRequest.value = request
}
function closeModal() {
  modalRequest.value = null
}
</script>

<template>
  <div class="h-screen flex flex-col bg-white">
    <header class="border-b border-gray-200 p-3 flex items-center gap-4 shrink-0">
      <h1 class="font-semibold text-gray-900 text-sm shrink-0">Расписание</h1>
      <div class="flex gap-1 bg-gray-100 rounded-md p-0.5">
        <button
          v-for="mode in [
            { value: 'group', label: 'По группам' },
            { value: 'room', label: 'По аудиториям' },
            { value: 'teacher', label: 'По преподавателям' },
          ]"
          :key="mode.value"
          class="px-3 py-1 text-sm rounded transition-colors"
          :class="
            store.viewMode === mode.value
              ? 'bg-white shadow-sm text-gray-900 font-medium'
              : 'text-gray-500 hover:text-gray-800'
          "
          @click="store.setViewMode(mode.value)"
        >
          {{ mode.label }}
        </button>
      </div>
      <select
        v-model="store.selectedId"
        class="border border-gray-300 rounded-md text-sm px-2 py-1"
      >
        <option v-for="opt in store.entityOptions" :key="opt.id" :value="opt.id">
          {{ opt.label }}
        </option>
      </select>
    </header>

    <div v-if="store.error" class="bg-red-50 text-red-700 text-sm px-3 py-2 border-b border-red-200">
      {{ store.error }}
    </div>

    <div class="flex flex-1 min-h-0">
      <LoadPool />
      <ScheduleGrid @drop-request="onDropRequest" />
    </div>

    <RoomPickerModal :request="modalRequest" @close="closeModal" />
  </div>
</template>
