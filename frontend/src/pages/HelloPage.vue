<template>
  <div class="p-6">
    <h1 class="text-2xl font-bold mb-4">Hello Page</h1>
    <div class="bg-white rounded-lg shadow p-6">
      <p class="mb-4">This is a custom Hello page demonstrating the full-stack development workflow in Frappe CRM.</p>
      <div v-if="loading" class="text-gray-500">Loading message from backend...</div>
      <div v-else class="bg-blue-50 p-4 rounded-lg border border-blue-200">
        <p class="font-medium">Message from backend:</p>
        <p class="text-blue-700 font-bold mt-2">{{ message }}</p>
      </div>
      <button 
        @click="fetchMessage" 
        class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        Refresh Message
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { createResource } from 'frappe-ui'

const message = ref('')
const loading = ref(true)

const helloResource = createResource({
  url: 'crm.api.hello.get_hello_message',
  onSuccess: (data) => {
    message.value = data.message
    loading.value = false
  },
  onError: (error) => {
    console.error('Error fetching hello message:', error)
    message.value = 'Error fetching message from backend'
    loading.value = false
  }
})

function fetchMessage() {
  loading.value = true
  helloResource.submit()
}

onMounted(() => {
  fetchMessage()
})
</script>
