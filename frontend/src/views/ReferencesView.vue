<script setup>
import { ref } from 'vue'
import { useScheduleStore } from '../stores/schedule'
import EntityTable from '../components/EntityTable.vue'
import LoadEditor from '../components/LoadEditor.vue'

const store = useScheduleStore()
const tab = ref('buildings')

const tabs = [
  { key: 'buildings', label: 'Корпуса' },
  { key: 'rooms', label: 'Аудитории' },
  { key: 'teachers', label: 'Преподаватели' },
  { key: 'groups', label: 'Группы' },
  { key: 'subjects', label: 'Предметы' },
  { key: 'timeSlots', label: 'Слоты' },
  { key: 'loads', label: 'Нагрузка' },
]

const buildingFields = [{ key: 'name', label: 'Название', type: 'text' }]

const roomFields = [
  {
    key: 'building_id',
    label: 'Корпус',
    type: 'select',
    options: () => store.buildings.map((b) => ({ value: b.id, label: b.name })),
  },
  { key: 'number', label: 'Номер', type: 'text' },
  { key: 'capacity', label: 'Вместимость', type: 'number' },
  { key: 'floor', label: 'Этаж', type: 'number' },
  { key: 'is_lab', label: 'Лаборатория', type: 'checkbox' },
]

const teacherFields = [
  { key: 'full_name', label: 'ФИО', type: 'text' },
  { key: 'department', label: 'Кафедра', type: 'text' },
]

const groupFields = [
  { key: 'code', label: 'Код', type: 'text' },
  { key: 'students_count', label: 'Студентов', type: 'number' },
  { key: 'course', label: 'Курс', type: 'number' },
]

const subjectFields = [{ key: 'name', label: 'Название', type: 'text' }]

const timeSlotFields = [
  { key: 'slot_number', label: '№ пары', type: 'number' },
  { key: 'start_time', label: 'Начало', type: 'text' },
  { key: 'end_time', label: 'Конец', type: 'text' },
]
</script>

<template>
  <div class="flex-1 overflow-auto">
    <div class="flex flex-wrap gap-1 bg-gray-100 rounded-md p-0.5 m-3 w-fit">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="px-3 py-1 text-sm rounded transition-colors"
        :class="
          tab === t.key
            ? 'bg-white shadow-sm text-gray-900 font-medium'
            : 'text-gray-500 hover:text-gray-800'
        "
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <EntityTable
      v-if="tab === 'buildings'"
      entity="buildings"
      title="Корпуса"
      :items="store.buildings"
      :fields="buildingFields"
    />
    <EntityTable
      v-else-if="tab === 'rooms'"
      entity="rooms"
      title="Аудитории"
      :items="store.rooms"
      :fields="roomFields"
    />
    <EntityTable
      v-else-if="tab === 'teachers'"
      entity="teachers"
      title="Преподаватели"
      :items="store.teachers"
      :fields="teacherFields"
    />
    <EntityTable
      v-else-if="tab === 'groups'"
      entity="groups"
      title="Группы"
      :items="store.groups"
      :fields="groupFields"
    />
    <EntityTable
      v-else-if="tab === 'subjects'"
      entity="subjects"
      title="Предметы"
      :items="store.subjects"
      :fields="subjectFields"
    />
    <EntityTable
      v-else-if="tab === 'timeSlots'"
      entity="timeSlots"
      title="Временные слоты"
      :items="store.timeSlots"
      :fields="timeSlotFields"
    />
    <LoadEditor v-else-if="tab === 'loads'" />
  </div>
</template>
