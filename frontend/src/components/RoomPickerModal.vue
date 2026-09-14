<script setup>
import { ref, computed, watch } from 'vue'
import { useScheduleStore, DAYS } from '../stores/schedule'

const props = defineProps({
  // { loadId, itemId, day, slotId } | null
  request: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const store = useScheduleStore()
const roomResults = ref([]) // [{ room, status: 'ok' | 'warn' | 'error', messages: [] }]
const loadingRooms = ref(false)

const load = computed(() => (props.request ? store.loadById(props.request.loadId) : null))
const dayLabel = computed(() => DAYS.find((d) => d.value === props.request?.day)?.label ?? '')
const slot = computed(() => (props.request ? store.timeSlotById(props.request.slotId) : null))

watch(
  () => props.request,
  async (req) => {
    if (!req) {
      roomResults.value = []
      return
    }
    loadingRooms.value = true
    const results = await Promise.all(
      store.rooms.map(async (room) => {
        const data = await store.validateRoom(req.loadId, req.itemId, req.day, req.slotId, room.id)
        let status = 'ok'
        if (!data.is_valid) status = 'error'
        else if (data.warnings.length > 0) status = 'warn'
        return { room, status, messages: [...data.errors, ...data.warnings] }
      }),
    )
    const studentsTotal = store.loadById(req.loadId)?.students_total ?? 0
    const rank = { ok: 0, warn: 1, error: 2 }
    results.sort((a, b) => {
      if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status]
      if (a.status === 'ok') return a.room.capacity - studentsTotal - (b.room.capacity - studentsTotal)
      if (a.status === 'warn') return b.room.capacity - a.room.capacity
      return 0
    })
    roomResults.value = results
    loadingRooms.value = false
  },
  { immediate: true },
)

function close() {
  emit('close')
}

async function pickRoom(result) {
  if (result.status === 'error' || !props.request) return
  try {
    await store.assign({
      loadId: props.request.loadId,
      itemId: props.request.itemId,
      day: props.request.day,
      timeSlotId: props.request.slotId,
      roomId: result.room.id,
    })
    close()
  } catch {
    // store.error is set and shown by the parent's error banner; keep the
    // modal open so the user can pick a different room.
  }
}

function onKeydown(event) {
  if (event.key === 'Escape' && props.request) close()
}
watch(
  () => !!props.request,
  (isOpen) => {
    if (isOpen) window.addEventListener('keydown', onKeydown)
    else window.removeEventListener('keydown', onKeydown)
  },
)
</script>

<template>
  <div
    v-if="request"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="close"
  >
    <div class="bg-white rounded-lg shadow-xl w-96 max-h-[80vh] flex flex-col">
      <div class="p-4 border-b border-gray-200">
        <h3 class="font-semibold text-gray-900">{{ store.subjectById(load?.subject_id)?.name }}</h3>
        <p class="text-sm text-gray-500">
          {{ dayLabel }}, {{ slot?.slot_number }} пара ({{ slot?.start_time }}–{{ slot?.end_time }}) ·
          {{ load?.students_total }} студ.
        </p>
      </div>
      <div class="overflow-y-auto p-2 space-y-1">
        <p v-if="loadingRooms" class="text-sm text-gray-400 p-2">Проверяем аудитории…</p>
        <button
          v-for="result in roomResults"
          :key="result.room.id"
          :disabled="result.status === 'error'"
          class="w-full text-left rounded-md p-2 border text-sm flex flex-col gap-0.5 transition-colors"
          :class="{
            'border-green-300 bg-green-50 hover:bg-green-100 cursor-pointer': result.status === 'ok',
            'border-amber-300 bg-amber-50 hover:bg-amber-100 cursor-pointer': result.status === 'warn',
            'border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed': result.status === 'error',
          }"
          @click="pickRoom(result)"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium">
              {{ result.room.number }}
              <span
                v-if="result.room.is_lab"
                class="text-[10px] ml-1 px-1 rounded bg-amber-200 text-amber-900"
              >
                Лаб
              </span>
            </span>
            <span>{{ result.room.capacity }} мест · {{ result.room.floor }} этаж</span>
          </div>
          <div v-if="result.messages.length > 0" class="text-xs">
            {{ result.messages.join('; ') }}
          </div>
        </button>
      </div>
      <div class="p-3 border-t border-gray-200 flex justify-end">
        <button class="text-sm text-gray-500 hover:text-gray-800 px-3 py-1" @click="close">
          Отмена
        </button>
      </div>
    </div>
  </div>
</template>
