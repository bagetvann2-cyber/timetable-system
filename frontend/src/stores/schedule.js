import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const DAYS = [
  { value: 1, label: 'Пн' },
  { value: 2, label: 'Вт' },
  { value: 3, label: 'Ср' },
  { value: 4, label: 'Чт' },
  { value: 5, label: 'Пт' },
  { value: 6, label: 'Сб' },
]

export const LESSON_TYPE_LABELS = {
  lecture: 'Лекция',
  practice: 'Практика',
  lab: 'Лаб',
}

export const useScheduleStore = defineStore('schedule', () => {
  const buildings = ref([])
  const rooms = ref([])
  const teachers = ref([])
  const groups = ref([])
  const subjects = ref([])
  const timeSlots = ref([])
  const loads = ref([])
  const items = ref([])

  const viewMode = ref('group') // 'group' | 'room' | 'teacher'
  const selectedId = ref(null)

  const dragging = ref(null) // { loadId, itemId: number | null } | null
  const cellCache = ref(new Map()) // "day-slot" -> { is_valid, errors, warnings }

  const loading = ref(false)
  const error = ref('')

  // --- lookups -------------------------------------------------------

  function loadById(id) {
    return loads.value.find((l) => l.id === id) ?? null
  }
  function subjectById(id) {
    return subjects.value.find((s) => s.id === id) ?? null
  }
  function teacherById(id) {
    return teachers.value.find((t) => t.id === id) ?? null
  }
  function groupById(id) {
    return groups.value.find((g) => g.id === id) ?? null
  }
  function roomById(id) {
    return rooms.value.find((r) => r.id === id) ?? null
  }
  function timeSlotById(id) {
    return timeSlots.value.find((t) => t.id === id) ?? null
  }
  function groupCodes(groupIds) {
    return groupIds.map((id) => groupById(id)?.code ?? '?').join(', ')
  }

  function remaining(load) {
    const placed = items.value.filter((i) => i.academic_load_id === load.id).length
    return load.total_hours_per_week - placed
  }

  const entityOptions = computed(() => {
    if (viewMode.value === 'group') {
      return groups.value.map((g) => ({ id: g.id, label: g.code }))
    }
    if (viewMode.value === 'teacher') {
      return teachers.value.map((t) => ({ id: t.id, label: t.full_name }))
    }
    return rooms.value.map((r) => ({ id: r.id, label: r.number }))
  })

  const poolLoads = computed(() => {
    const unfinished = loads.value.filter((l) => remaining(l) > 0)
    if (viewMode.value === 'group') {
      return unfinished.filter((l) => l.group_ids.includes(selectedId.value))
    }
    if (viewMode.value === 'teacher') {
      return unfinished.filter((l) => l.teacher_id === selectedId.value)
    }
    return unfinished
  })

  function itemAt(day, timeSlotId) {
    const candidates = items.value.filter(
      (i) => i.day_of_week === day && i.time_slot_id === timeSlotId,
    )
    if (viewMode.value === 'room') {
      return candidates.find((i) => i.room_id === selectedId.value) ?? null
    }
    return (
      candidates.find((i) => {
        const load = loadById(i.academic_load_id)
        if (!load) return false
        if (viewMode.value === 'teacher') return load.teacher_id === selectedId.value
        return load.group_ids.includes(selectedId.value)
      }) ?? null
    )
  }

  // --- data loading ----------------------------------------------------

  async function load() {
    loading.value = true
    try {
      const { data } = await axios.get('/api/initial-data')
      buildings.value = data.buildings
      rooms.value = data.rooms
      teachers.value = data.teachers
      groups.value = data.groups
      subjects.value = data.subjects
      timeSlots.value = data.time_slots
      loads.value = data.loads
      items.value = data.items
      error.value = ''
      if (selectedId.value === null && entityOptions.value.length > 0) {
        selectedId.value = entityOptions.value[0].id
      }
    } catch (e) {
      error.value = 'Бэкенд недоступен — запустите uvicorn (см. README)'
      throw e
    } finally {
      loading.value = false
    }
  }

  function setViewMode(mode) {
    viewMode.value = mode
    selectedId.value = entityOptions.value.length > 0 ? entityOptions.value[0].id : null
  }

  // --- validation --------------------------------------------------------

  // loadId/itemId are passed explicitly (not read from `dragging`) because
  // `dragging` is cleared by the `dragend` event, which can fire before the
  // room-picker modal's own validateRoom calls resolve.
  async function validateCell(loadId, itemId, day, timeSlotId) {
    const key = `${day}-${timeSlotId}`
    if (cellCache.value.has(key)) return cellCache.value.get(key)
    const { data } = await axios.post('/api/schedule/validate', {
      academic_load_id: loadId,
      day_of_week: day,
      time_slot_id: timeSlotId,
      current_item_id: itemId,
    })
    cellCache.value.set(key, data)
    return data
  }

  async function validateRoom(loadId, itemId, day, timeSlotId, roomId) {
    const { data } = await axios.post('/api/schedule/validate', {
      academic_load_id: loadId,
      day_of_week: day,
      time_slot_id: timeSlotId,
      room_id: roomId,
      current_item_id: itemId,
    })
    return data
  }

  // --- mutations -----------------------------------------------------

  async function assign({ loadId, itemId, day, timeSlotId, roomId }) {
    try {
      await axios.post('/api/schedule/assign', {
        academic_load_id: loadId,
        day_of_week: day,
        time_slot_id: timeSlotId,
        room_id: roomId,
        current_item_id: itemId,
      })
      error.value = ''
      await load()
    } catch (e) {
      const detail = e.response?.data?.detail
      error.value = detail?.errors?.join('; ') || 'Не удалось поставить пару'
      throw e
    }
  }

  async function unassign(itemId) {
    try {
      await axios.delete(`/api/schedule/unassign/${itemId}`)
      error.value = ''
      await load()
    } catch (e) {
      error.value = 'Не удалось убрать пару'
      throw e
    }
  }

  function startDrag(loadId, itemId = null) {
    dragging.value = { loadId, itemId }
  }
  function endDrag() {
    dragging.value = null
    cellCache.value = new Map()
  }

  return {
    buildings,
    rooms,
    teachers,
    groups,
    subjects,
    timeSlots,
    loads,
    items,
    viewMode,
    selectedId,
    dragging,
    cellCache,
    loading,
    error,
    entityOptions,
    poolLoads,
    loadById,
    subjectById,
    teacherById,
    groupById,
    roomById,
    timeSlotById,
    groupCodes,
    remaining,
    itemAt,
    load,
    setViewMode,
    validateCell,
    validateRoom,
    assign,
    unassign,
    startDrag,
    endDrag,
  }
})
