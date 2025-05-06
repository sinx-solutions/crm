<template>
  <Dialog
    v-model="show"
    :options="{
      title: __('AI Email Process Logs'),
      size: 'xl',
    }"
  >
    <template #body-content>
      <div class="p-2">
        <div v-if="loading" class="flex justify-center py-4">
          <div class="loading-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
        <div v-else-if="error" class="rounded-md bg-ink-red-1 p-4">
          <p class="text-ink-red-9">{{ error }}</p>
        </div>
        <div v-else>
          <div class="mb-4 flex justify-between">
            <p class="text-sm text-ink-gray-6">
              {{ __('Showing the latest {0} log entries for AI email processes', [100]) }}
            </p>
            <div class="flex items-center gap-3">
              <FormControl
                type="checkbox"
                v-model="showEmailContent"
                :label="__('Show Email Content')"
              />
              <Button
                :label="__('Refresh')"
                variant="subtle"
                size="sm"
                @click="fetchLogs"
                :loading="refreshing"
              />
            </div>
          </div>
          <div v-if="logs.length === 0" class="py-4 text-center text-ink-gray-6">
            {{ __('No logs found') }}
          </div>
          <div v-else class="max-h-[70vh] overflow-y-auto rounded border border-ink-gray-2 bg-ink-gray-1 p-2 font-mono text-xs">
            <div
              v-for="(log, index) in logs"
              :key="index"
              :class="{
                'mb-1 border-b border-ink-gray-2 pb-1 last:border-b-0 last:pb-0': true,
                'stage-header': isStageHeader(log.message),
                'process-header': isProcessHeader(log.message),
                'process-footer': isProcessFooter(log.message),
                'summary-section': isSummarySection(log.message),
                'email-content': isEmailContent(log.message) && showEmailContent,
                'hidden': isEmailContent(log.message) && !showEmailContent
              }"
            >
              <div class="flex items-start">
                <span class="mr-2 text-ink-gray-5 whitespace-nowrap">{{ formatTimestamp(log.timestamp) }}</span>
                <span 
                  :class="{
                    'text-ink-gray-8': !getMessageType(log.message),
                    'text-ink-red-9 font-semibold': getMessageType(log.message) === 'error',
                    'text-ink-green-9 font-semibold': getMessageType(log.message) === 'success',
                    'text-ink-blue-9 font-semibold': getMessageType(log.message) === 'stage',
                    'text-ink-purple-9 font-semibold': getMessageType(log.message) === 'process',
                    'text-ink-yellow-9 font-semibold': getMessageType(log.message) === 'summary',
                    'text-ink-gray-7 italic': getMessageType(log.message) === 'detail',
                    'text-ink-teal-9 font-semibold': getMessageType(log.message) === 'ai-content',
                    'whitespace-pre-wrap': isEmailContent(log.message),
                    'font-normal': isEmailContent(log.message),
                  }"
                >
                  {{ formatMessage(log.message) }}
                </span>
              </div>
            </div>
          </div>
          <div class="mt-4">
            <p class="text-sm text-ink-gray-6">
              {{ __('For complete logs, check the server logs at logs/ai_email.log') }}
            </p>
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-between w-full">
        <Button :label="__('Close')" @click="show = false" />
        <div>
          <FormControl
            type="checkbox"
            v-model="autoRefresh"
            :label="__('Auto-refresh (5s)')"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Dialog, Button, FormControl, createResource } from 'frappe-ui'
import { __ } from '@/utils/translations'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const show = defineModel()
const logs = ref([])
const loading = ref(false)
const refreshing = ref(false)
const error = ref(null)
const autoRefresh = ref(true)
const showEmailContent = ref(true)
let refreshInterval = null

// Helper functions for log formatting
function isStageHeader(message) {
  return message.includes('[STAGE ') || message.includes('[AI EMAIL GENERATED SUCCESSFULLY]')
}

function isProcessHeader(message) {
  return message.includes('========== PROCESSING LEAD:')
}

function isProcessFooter(message) {
  return message.includes('========== COMPLETED PROCESSING LEAD:')
}

function isSummarySection(message) {
  return message.includes('BULK EMAIL PROCESS SUMMARY')
}

function isEmailContent(message) {
  return message.includes('CONTENT START') || 
         message.includes('CONTENT END') ||
         (logs.value.some(l => l.message.includes('CONTENT START')) && 
          !message.includes('CONTENT START') && 
          !message.includes('CONTENT END') && 
          !message.includes('['))
}

function getMessageType(message) {
  if (message.includes('ERROR:')) return 'error'
  if (message.includes('SUCCESS:')) return 'success'
  if (message.includes('[STAGE ')) return 'stage'
  if (message.includes('========== PROCESSING') || message.includes('========== COMPLETED')) return 'process'
  if (message.includes('BULK EMAIL PROCESS SUMMARY') || message.includes('Total leads processed:')) return 'summary'
  if (message.includes('SUBJECT:') || message.includes('CONTENT START') || message.includes('CONTENT END')) return 'ai-content'
  if (message.includes(':') && !message.includes('==')) return 'detail'
  return null
}

function formatTimestamp(timestamp) {
  // Extract only the time portion for cleaner display
  if (!timestamp) return ''
  const parts = timestamp.split(' ')
  if (parts.length >= 2) {
    return parts[1] // Return only the time part
  }
  return timestamp
}

function formatMessage(message) {
  // Remove redundant prefixes for cleaner display
  return message.replace('AI Email: ', '')
}

// Set up auto-refresh
watch(autoRefresh, (value) => {
  if (value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

watch(show, (value) => {
  if (value) {
    fetchLogs()
    if (autoRefresh.value) {
      startAutoRefresh()
    }
  } else {
    stopAutoRefresh()
  }
})

function startAutoRefresh() {
  stopAutoRefresh() // Clear any existing interval
  refreshInterval = setInterval(() => {
    if (show.value) {
      fetchLogs(true)
    }
  }, 5000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

onMounted(() => {
  if (show.value) {
    fetchLogs()
    if (autoRefresh.value) {
      startAutoRefresh()
    }
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})

async function fetchLogs(isRefresh = false) {
  if (isRefresh) {
    refreshing.value = true
  } else {
    loading.value = true
  }
  
  error.value = null
  
  try {
    const response = await getEmailLogs.submit()
    
    if (response.success) {
      logs.value = response.logs
    } else {
      error.value = response.message || __('Failed to fetch logs')
    }
  } catch (err) {
    console.error('Error fetching logs:', err)
    error.value = err.message || __('An error occurred while fetching logs')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const getEmailLogs = createResource({
  url: 'crm.api.ai_email.get_ai_email_logs',
  params: {
    limit: 100
  }
})
</script>

<style scoped>
.loading-dots {
  display: flex;
  justify-content: center;
  align-items: center;
}
.loading-dots span {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #cbd5e1;
  margin: 0 5px;
  animation: dots 1.4s infinite ease-in-out both;
}
.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}
.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}
@keyframes dots {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.stage-header {
  margin-top: 8px;
  padding: 4px 0;
  border-top: 1px dashed #94a3b8;
  font-weight: 600;
}

.process-header {
  margin-top: 16px;
  padding: 6px 0;
  border-top: 2px solid #94a3b8;
  font-weight: 700;
  background-color: rgba(148, 163, 184, 0.1);
}

.process-footer {
  margin-bottom: 16px;
  padding: 6px 0;
  border-bottom: 2px solid #94a3b8;
  font-weight: 700;
  background-color: rgba(148, 163, 184, 0.1);
}

.summary-section {
  margin-top: 16px;
  padding: 6px;
  background-color: rgba(251, 191, 36, 0.1);
  font-weight: 600;
  border-radius: 4px;
}

.email-content {
  padding: 4px 8px;
  margin: 4px 0;
  background-color: rgba(248, 250, 252, 0.8);
  border-left: 4px solid #0ea5e9;
  white-space: pre-wrap;
}
</style> 