<template>
  <Dialog
    v-model="show"
    :options="{
      title: __('Bulk AI Email Generator'),
      size: 'lg',
    }"
  >
    <template #body-content>
      <div v-if="loading" class="flex flex-col items-center justify-center py-8">
        <div class="loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <p class="mt-4 text-center text-ink-gray-6">
          {{ __('Processing bulk emails...') }}
        </p>
      </div>
      <div v-else-if="error" class="rounded-md bg-ink-red-1 p-4 text-ink-red-9">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg
              class="h-5 w-5"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-ink-red-9">
              {{ __('Error') }}
            </h3>
            <div class="mt-2 text-sm text-ink-red-7">
              <p>{{ error }}</p>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="success" class="rounded-md bg-ink-green-1 p-4 text-ink-green-9">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg
              class="h-5 w-5"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-ink-green-9">
              {{ success }}
            </h3>
            <div class="mt-2 text-sm text-ink-green-9">
              <p>
                {{ __('The bulk email generation job has been started. Check for emails in the activity timeline of each lead.') }}
              </p>
              <p class="mt-2">
                {{ __('In test mode, all emails will be sent to the test email address.') }}
              </p>
              <p class="mt-2 font-medium">
                {{ __('Note: It may take a few minutes for all emails to be generated and appear in the timeline.') }}
              </p>
              <div class="mt-4 flex gap-2">
                <Button
                  :label="__('View Process Logs')"
                  variant="outline"
                  @click="showLogs"
                />
                <Button
                  :label="__('View Job Monitor')"
                  variant="outline"
                  @click="openJobMonitor"
                  v-if="currentJobId"
                />
              </div>
              <p class="mt-2 text-xs text-ink-gray-7">
                {{ __('View detailed logs of the email generation process') }}
              </p>
            </div>
          </div>
        </div>
      </div>
      <div v-else>
        <div v-if="props.selectedLeads?.length" class="mb-4 text-sm text-ink-gray-7">
          <div class="rounded-md bg-ink-blue-1 p-3">
            <p>{{ __('You have selected {0} lead(s) for email generation.', [props.selectedLeads.length]) }}</p>
          </div>
        </div>
        <div v-else class="mb-4 text-sm">
          <div class="rounded-md bg-ink-yellow-1 p-3 text-ink-yellow-9">
            <p>{{ __('No leads are selected. The system will use current list filters to select leads.') }}</p>
            <p class="mt-2 font-semibold">{{ __('This could potentially affect many leads. Use test mode first!') }}</p>
          </div>
        </div>
        <div class="mb-4">
          <FormControl
            type="select"
            v-model="tone"
            :label="__('Tone')"
            :options="toneOptions"
          />
        </div>
        <div class="mb-4">
          <FormControl
            type="textarea"
            v-model="additionalContext"
            :label="__('Additional Context (Optional)')"
            :placeholder="__('Add any specific instructions or context for the AI generator...')"
            :rows="3"
          />
        </div>
        <div class="mb-4">
          <FormControl
            type="checkbox"
            v-model="testMode"
            :label="__('Test Mode (Sends to your email instead of leads)')"
          />
          <div v-if="testMode" class="mt-1 text-sm text-ink-gray-6">
            {{ __('All emails will be sent to:') }} {{ testEmail }}
          </div>
        </div>
        <div class="flex justify-end space-x-2">
          <Button
            :label="__('Cancel')"
            variant="outline"
            @click="show = false"
          />
          <Button
            :label="__('Generate Emails')"
            variant="solid"
            :loading="loading"
            @click="generateEmails"
          />
        </div>
      </div>
    </template>
  </Dialog>
  
  <!-- Add the logs modal -->
  <AIEmailLogsModal v-model="showLogsModal" />
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Dialog, FormControl, Button, createResource, call } from 'frappe-ui'
import { __ } from '@/utils/translations'
import { capture } from '@/telemetry'
import AIEmailLogsModal from './AIEmailLogsModal.vue'
import { useRouter } from 'vue-router'
import { globalStore } from '@/stores/global'

const props = defineProps({
  selectedLeads: {
    type: Array,
    default: () => []
  },
  filters: {
    type: Object,
    default: () => ({})
  }
})

// Initialize socket and router
const { $socket } = globalStore()
const router = useRouter()

const show = defineModel()

const tone = ref('professional')
const additionalContext = ref('')
const testMode = ref(true)
const loading = ref(false)
const error = ref(null)
const success = ref(null)
const testEmail = ref('sanchayt@sinxsolutions.ai')
const apiStatus = ref(null)
const currentJobId = ref(null)

const toneOptions = [
  { label: __('Professional'), value: 'professional' },
  { label: __('Friendly'), value: 'friendly' },
  { label: __('Formal'), value: 'formal' },
  { label: __('Persuasive'), value: 'persuasive' }
]

const buttonDisabled = computed(() => {
  return apiStatus.value && !apiStatus.value.openai_configured;
})

const processedLeads = ref([])

// Setup socket listeners for real-time updates
function setupRealtimeListeners() {
  // Add debug logging for socket connection status
  console.log('=== WEBSOCKET DEBUG ===');
  console.log('Socket connected:', $socket.connected);
  console.log('Socket instance:', $socket);
  console.log('Setting up realtime listeners for bulk email events');

  // Log all incoming socket events for debugging
  $socket.onAny((event, ...args) => {
    console.log(`Socket event received: ${event}`, args);
  });
  
  // Add listener for test message
  $socket.on('bulk_email_test', (data) => {
    console.log('SOCKET TEST MESSAGE RECEIVED (DIRECT):', data);
    // Show as a notification if possible
    try {
      if (window.Notification && Notification.permission === "granted") {
        new Notification('Socket Test - Direct', { 
          body: 'Socket connection is working! Test message received.' 
        });
      }
    } catch (e) {
      console.error('Could not show notification:', e);
    }
  });
  
  // Add listener for user-specific test message
  $socket.on('bulk_email_test_user', (data) => {
    console.log('SOCKET TEST MESSAGE RECEIVED (USER SPECIFIC):', data);
  });
  
  // Add listener for room test message
  $socket.on('bulk_email_test_room', (data) => {
    console.log('SOCKET TEST MESSAGE RECEIVED (ROOM):', data);
  });
  
  // Listen for any bulk_* events
  $socket.on('bulk_*', (data) => {
    console.log('WILDCARD BULK EVENT RECEIVED:', data);
  });
  
  $socket.on('bulk_email_progress', (data) => {
    console.log('Bulk email progress update received:', data);
    
    // If this lead was processed successfully, add to processed list
    if (data.status === 'success') {
      processedLeads.value.push(data.lead);
      console.log('Updated processed leads list:', processedLeads.value);
      
      // If the current page is showing this lead, refresh the timeline
      const currentRoute = router.currentRoute.value;
      if (currentRoute.name === 'Lead' && currentRoute.params.id === data.lead) {
        console.log('Refreshing current lead page:', data.lead);
        // Trigger a reload of the document info for the lead
        refreshLeadTimeline(data.lead);
      }
    }
  });
  
  $socket.on('bulk_email_complete', (data) => {
    console.log('Bulk email process completed event received:', data);
    processedLeads.value = data.processed_leads || [];
    
    // Refresh current page if it's a lead page
    const currentRoute = router.currentRoute.value;
    if (currentRoute.name === 'Lead' && processedLeads.value.includes(currentRoute.params.id)) {
      refreshLeadTimeline(currentRoute.params.id);
    }
  });
  
  // Check if socket is connected and log status
  if (!$socket.connected) {
    console.warn('WARNING: Socket is not connected! Real-time updates will not work.');
    // Try reconnecting socket
    $socket.connect();
    console.log('Attempted to reconnect socket.');
  }
}

function cleanupRealtimeListeners() {
  $socket.off('bulk_email_progress')
  $socket.off('bulk_email_complete')
}

// Function to refresh the timeline for a lead
async function refreshLeadTimeline(leadId) {
  try {
    console.log('Refreshing lead timeline for:', leadId)
    // Get fresh document info via Frappe API
    await call('frappe.desk.form.load.get_docinfo', {
      doctype: 'CRM Lead',
      name: leadId
    })
    
    // Emit a custom event that can be captured by parent components
    $socket.emit('crm:refresh_timeline', { 
      doctype: 'CRM Lead', 
      name: leadId 
    })
    
    console.log('Timeline refresh triggered for lead:', leadId)
  } catch (err) {
    console.error('Error refreshing lead timeline:', err)
  }
}

onMounted(async () => {
  try {
    const response = await getApiStatus.submit();
    apiStatus.value = response;
    testEmail.value = response.test_email || testEmail.value;
    
    // Setup realtime listeners when component mounts
    setupRealtimeListeners()
  } catch (err) {
    console.error('Error checking API status:', err);
  }
})

onBeforeUnmount(() => {
  // Clean up event listeners when component unmounts
  cleanupRealtimeListeners()
})

// Add this new polling setup that doesn't rely on WebSockets
const POLLING_INTERVAL = 3000; // 3 seconds
let pollingTimer = null;

function startJobPolling(jobId) {
  console.log(`Starting to poll for job status: ${jobId}`);
  currentJobId.value = jobId;
  
  // Clear any existing timer
  if (pollingTimer) {
    clearInterval(pollingTimer);
  }
  
  // Setup polling for job status
  pollingTimer = setInterval(() => {
    checkJobStatus(jobId);
  }, POLLING_INTERVAL);
  
  // Initial check immediately
  checkJobStatus(jobId);
}

function stopJobPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

const checkJobStatus = async (jobId) => {
  try {
    const result = await call('crm.api.ai_email.get_bulk_email_job_status', {
      job_id: jobId
    });
    
    if (result.success) {
      const jobData = result.job_data;
      console.log('Job status update:', jobData);
      
      // Update processed leads if available
      if (jobData.successful_leads && jobData.successful_leads.length > 0) {
        processedLeads.value = jobData.successful_leads;
      }
      
      // Check if job is completed
      if (jobData.status === 'finished' || jobData.status === 'failed') {
        if (jobData.progress >= 100) {
          // Stop polling after a few more checks to ensure we get all updates
          setTimeout(() => {
            stopJobPolling();
          }, POLLING_INTERVAL * 3);
        }
      }
    }
  } catch (error) {
    console.error('Error checking job status:', error);
  }
};

// Cleanup polling on component unmount
onBeforeUnmount(() => {
  stopJobPolling();
});

// Update the generateEmails function to use the new polling mechanism
const generateEmails = async () => {
  loading.value = true;
  error.value = null;
  success.value = null;
  
  try {
    // Create filter JSON string if leads are selected
    let filterJson = null;
    if (props.selectedLeads && props.selectedLeads.length > 0) {
      // Extract just the lead names for the filter
      const leadNames = props.selectedLeads.map(lead => lead.name);
      console.log('Selected lead names:', leadNames);
      
      // Format as a "name is in [...]" filter
      filterJson = JSON.stringify({
        name: ["in", leadNames]
      });
      console.log('Using filter JSON:', filterJson);
    } else {
      // Use the current list filters if no leads are selected
      filterJson = JSON.stringify(props.filters || {});
    }
    
    // Track event in analytics
    capture('bulk_ai_email_generate', {
      leads_count: props.selectedLeads?.length || 0,
      tone: tone.value,
      test_mode: testMode.value
    });
    
    // Call the API to generate emails
    const result = await call('crm.api.ai_email.generate_bulk_emails', {
      filter_json: filterJson,
      tone: tone.value,
      additional_context: additionalContext.value,
      test_mode: testMode.value ? 1 : 0
    });
    
    if (result.success) {
      success.value = __('Bulk email generation started successfully!');
      console.log('Job ID for monitoring:', result.job_id);
      
      // Start polling for updates
      startJobPolling(result.job_id);
    } else {
      error.value = result.message || __('Failed to start bulk email generation');
    }
  } catch (err) {
    error.value = err.message || __('An error occurred');
    console.error('Error generating bulk emails:', err);
  } finally {
    loading.value = false;
  }
};

const generateBulkEmails = createResource({
  url: 'crm.api.ai_email.generate_bulk_emails',
  validate(values) {
    return null;
  }
});

const getApiStatus = createResource({
  url: 'crm.api.ai_email.get_api_status'
});

const showLogsModal = ref(false)

function showLogs() {
  showLogsModal.value = true
}

function openJobMonitor() {
  const monitorUrl = `/job_monitor${currentJobId.value ? '?job_id=' + currentJobId.value : ''}`;
  window.open(monitorUrl, '_blank');
}
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
</style>