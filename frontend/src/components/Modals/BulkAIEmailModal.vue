<template>
  <Dialog
    v-model="show"
    :options="{
      title: __('Bulk Email Sender'),
      size: 'lg',
    }"
  >
    <template #body-content>
      <div v-if="generateEmailsResource.loading.value || emailTemplates.loading.value" class="flex flex-col items-center justify-center py-8">
        <div class="loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <p class="mt-4 text-center text-ink-gray-6">
          {{ emailTemplates.loading.value ? __('Loading templates...') : __('Processing bulk emails...') }}
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
                {{ __('The bulk email job has been started using the selected template.') }}
              </p>
              <p class="mt-2">
                {{ __('In test mode, all emails will be sent to:') }} {{ testEmail }}
              </p>
              <p class="mt-2 font-medium">
                {{ __('Note: It may take a few minutes for all emails to be generated and appear in the timeline.') }}
              </p>
              <div class="mt-4 flex gap-2">
                <Button
                  :label="__('View Job Monitor')"
                  variant="outline"
                  @click="openJobMonitor"
                  v-if="currentJobId"
                />
              </div>
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
            v-model="selectedTemplateName"
            :label="__('Select Email Template')"
            :options="emailTemplateOptions"
            :placeholder="__('Choose an email template...')"
            :required="true"
            :loading="emailTemplates.loading.value"
          />
          <div v-if="emailTemplates.error.value" class="mt-1 text-xs text-red-600">
            {{ __('Error loading templates:') }} {{ emailTemplates.error.value.message }}
          </div>
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
            :label="__('Send Bulk Emails')"
            variant="solid"
            :loading="generateEmailsResource.loading.value"
            :disabled="!selectedTemplateName || generateEmailsResource.loading.value || emailTemplates.loading.value"
            @click="() => { console.log('[BulkEmailModal Button Click]'); generateEmails(); }"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed, onMounted, watch, onBeforeUnmount } from 'vue'
import { Dialog, FormControl, Button, createResource, call, createListResource } from 'frappe-ui'
import { __ } from '@/utils/translations'
import { capture } from '@/telemetry'
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

const { $socket } = globalStore()
const router = useRouter()

const show = defineModel()

const selectedTemplateName = ref(null)
const testMode = ref(true)
const error = ref(null)
const success = ref(null)
const testEmail = ref('sanchayt@sinxsolutions.ai')
const currentJobId = ref(null)

// NEW: Flag to track component mount status
const isMounted = ref(false)

const getUserEmail = createResource({
  url: 'frappe.client.get_value',
  makeParams: () => {
    if (window.frappe?.session?.user) {
      console.log("[BulkEmailModal DEBUG] getUserEmail makeParams: Creating params with user:", window.frappe.session.user);
      return {
        doctype: 'User',
        filters: { name: window.frappe.session.user },
        fieldname: 'email'
      };
    } else {
      console.warn("[BulkEmailModal DEBUG] getUserEmail makeParams: frappe.session.user not available yet. Skipping API call.");
      return null;
    }
  },
  onSuccess(data) {
    console.log("[BulkEmailModal DEBUG] getUserEmail onSuccess RAW data:", JSON.stringify(data));
    
    if (!isMounted.value) {
      console.warn("[BulkEmailModal DEBUG] getUserEmail onSuccess: Component unmounted before callback executed. Skipping assignment.");
      return;
    }
    
    let userEmail = null;
    if (data && data.message && typeof data.message.email === 'string') {
      userEmail = data.message.email;
      console.log("[BulkEmailModal DEBUG] getUserEmail onSuccess: Found email via data.message.email");
    } else if (data && typeof data.message === 'string') {
      if (data.message.includes('@')) {
        userEmail = data.message;
        console.log("[BulkEmailModal DEBUG] getUserEmail onSuccess: Found email via data.message");
      } else {
        console.warn("[BulkEmailModal DEBUG] getUserEmail onSuccess: data.message is a string but not an email:", data.message);
      }
    } else {
      console.warn("[BulkEmailModal DEBUG] getUserEmail onSuccess: Could not extract email from response structure:", data);
    }
    
    if (userEmail) {
      testEmail.value = userEmail;
      console.log("[BulkEmailModal] Default test email set to user email:", testEmail.value);
    } else {
      console.warn("[BulkEmailModal] Did not find user email in response, keeping default test email.");
    }
  },
  onError(err) {
    console.error("[BulkEmailModal DEBUG] getUserEmail onError:", err);
  }
})

const emailTemplates = createListResource({
  doctype: 'Email Template',
  fields: ['name', 'subject'],
  filters: { enabled: 1 },
  orderBy: 'name asc',
  limit: 0,
  onError(err) {
    console.error("[BulkEmailModal] Error fetching email templates:", err)
    error.value = `Failed to load email templates: ${err.message}`
  }
})

const emailTemplateOptions = computed(() => {
  if (!emailTemplates.data) return []
  return emailTemplates.data.map(template => ({
    label: `${template.name} (Subject: ${template.subject || 'N/A'})`,
    value: template.name
  }))
})

watch(show, (newValue) => {
  if (newValue && !emailTemplates.data && !emailTemplates.loading.value) {
    console.log("[BulkEmailModal] Modal opened, fetching email templates.")
    emailTemplates.fetch()
  }
})

const generateEmailsResource = createResource({
  url: 'crm.api.ai_email.generate_bulk_emails',
  makeParams: () => {
    console.log("[BulkEmailModal DEBUG] generateEmailsResource: makeParams called.")
    const params = {
      selected_leads: props.selectedLeads?.length ? JSON.stringify(props.selectedLeads.map(l => l.name)) : null,
      filter_json: !props.selectedLeads?.length ? JSON.stringify(props.filters || {}) : null,
      selected_template_name: selectedTemplateName.value,
      test_mode: testMode.value ? 1 : 0
    }
    console.log("[BulkEmailModal DEBUG] generateEmailsResource: Params created:", params)
    return params
  },
  onSuccess: (response) => {
    console.log("[BulkEmailModal DEBUG] generateEmailsResource: onSuccess triggered. Response:", response)
    if (response && response.job_id) {
      currentJobId.value = response.job_id
      success.value = response.message || __('Bulk email job started successfully.')
      error.value = null
      console.log("[BulkEmailModal] Job started successfully:", response.job_id)
      startJobPolling(response.job_id)
      capture('bulk_email_job_initiated', { template: selectedTemplateName.value, test_mode: testMode.value })
    } else {
      const errorMsg = (response && response.message) ? response.message : __('Failed to start bulk email job (invalid response).')
      error.value = errorMsg
      success.value = null
      console.error("[BulkEmailModal] Job initiation failed or received invalid response:", response)
      capture('bulk_email_job_error', { error: errorMsg })
    }
  },
  onError: (err) => {
    console.error("[BulkEmailModal DEBUG] generateEmailsResource: onError triggered. Error:", err)
    error.value = err.message || __('An error occurred while starting the bulk email job.')
    success.value = null
    capture('bulk_email_job_error', { error: err.message })
  }
})

function generateEmails() {
  console.log("[BulkEmailModal DEBUG] generateEmails function started.")
  if (!selectedTemplateName.value) {
    console.warn("[BulkEmailModal DEBUG] generateEmails: No template selected.")
    error.value = __('Please select an email template.')
    return
  }
  error.value = null
  success.value = null
  console.log(`[BulkEmailModal DEBUG] Submitting job request with template: ${selectedTemplateName.value}, TestMode: ${testMode.value}`)
  try {
    generateEmailsResource.submit()
    console.log("[BulkEmailModal DEBUG] generateEmailsResource.submit() called.")
  } catch (submitError) {
    console.error("[BulkEmailModal DEBUG] Error calling generateEmailsResource.submit():", submitError)
    error.value = `Client-side error submitting job: ${submitError.message}`
  }
}

const POLLING_INTERVAL = 5000
let pollingTimer = null

function startJobPolling(jobId) {
  console.log(`[BulkEmailModal] Starting polling for job: ${jobId}`)
  currentJobId.value = jobId
  stopJobPolling()

  pollingTimer = setInterval(() => {
    checkJobStatus(jobId)
  }, POLLING_INTERVAL)
  checkJobStatus(jobId)
}

function stopJobPolling() {
  if (pollingTimer) {
    console.log(`[BulkEmailModal] Stopping polling.`)
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

const checkJobStatus = async (jobId) => {
  if (!jobId) return
  try {
    const result = await call('crm.api.ai_email.get_bulk_email_job_status', {
      job_id: jobId
    })
    
    if (result.success && result.job_data) {
      const jobData = result.job_data
      console.log('[BulkEmailModal] Job status poll result:', jobData)
      
      if (jobData.status === 'finished' || jobData.status === 'completed' || jobData.status === 'failed') {
        console.log(`[BulkEmailModal] Job ${jobId} finished with status: ${jobData.status}`)
        stopJobPolling()
        if (jobData.status === 'failed') {
          error.value = jobData.error || __('Job failed. Check Job Monitor for details.')
          success.value = null
        } else {
          let finalMsg = `Job completed. Successful: ${jobData.successful_leads?.length || 0}. Failed: ${jobData.failed_leads?.length || 0}.`
          if (jobData.failed_leads?.length > 0) finalMsg += " Check Job Monitor for failed items."
          success.value = finalMsg
        }
      }
    } else {
      console.warn("[BulkEmailModal] Failed to get job status update:", result.message)
    }
  } catch (error) {
    console.error('[BulkEmailModal] Error during job status polling:', error)
  }
}

function openJobMonitor() {
  if (currentJobId.value) {
    window.open(`/app/background-job?name=${currentJobId.value}`, '_blank')
  }
}

onMounted(() => {
  console.log("[BulkEmailModal DEBUG] Entering onMounted.");
  isMounted.value = true; // Set mounted flag
  
  const setupFrappeDependent = () => {
    console.log("[BulkEmailModal DEBUG] setupFrappeDependent: Checking for window.frappe...");
    if (window.frappe?.session?.user) {
      console.log("[BulkEmailModal DEBUG] setupFrappeDependent: window.frappe found. User:", window.frappe.session.user);
      
      // --- CHECK IF MOUNTED before submitting ---
      if (!isMounted.value) {
        console.warn("[BulkEmailModal DEBUG] Component unmounted before submitting getUserEmail.");
        return;
      }
      
      if (getUserEmail && !getUserEmail.fetched) {
        console.log("[BulkEmailModal DEBUG] Submitting getUserEmail resource.");
        getUserEmail.submit();
      } else {
        console.log("[BulkEmailModal DEBUG] getUserEmail already fetched or resource invalid.");
      }
    } else {
      console.warn("[BulkEmailModal DEBUG] setupFrappeDependent: window.frappe not ready yet. Retrying...");
      // --- CHECK IF MOUNTED before scheduling retry ---
      if (isMounted.value) {
        setTimeout(setupFrappeDependent, 300);
      } else {
        console.warn("[BulkEmailModal DEBUG] Component unmounted, not scheduling retry.");
      }
    }
  };

  if (show.value && !emailTemplates.data && !emailTemplates.loading.value) {
    console.log("[BulkEmailModal DEBUG] Fetching templates in onMounted.");
    emailTemplates.fetch();
  }
  
  // Start the process to get user email
  setupFrappeDependent();
  
  console.log("[BulkEmailModal DEBUG] Exiting onMounted.");
});

onBeforeUnmount(() => {
  console.log("[BulkEmailModal DEBUG] Running onBeforeUnmount, stopping polling and setting isMounted=false.");
  isMounted.value = false; // Clear mounted flag
  stopJobPolling();
});
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