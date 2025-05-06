<template>
  <Dialog
    v-model="show"
    :options="{
      title: __('AI Email Generator'),
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
          {{ __('Generating personalized email...') }}
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
      <div v-else class="flex flex-col gap-4">
        <div v-if="generatedEmail">
          <div class="mb-4">
            <div class="flex justify-between mb-2">
              <h3 class="text-md font-medium">{{ __('Generated Email') }}</h3>
              <div class="flex space-x-2">
                <Button
                  :label="__('Send Test')"
                  variant="outline"
                  @click="sendTestEmail"
                  :loading="testEmailLoading"
                />
                <Button
                  :label="__('Use This')"
                  variant="solid"
                  @click="useGeneratedEmail"
                />
              </div>
            </div>
            <div class="mb-2">
              <label class="block text-sm font-medium mb-1">{{ __('Subject') }}</label>
              <input
                type="text"
                v-model="generatedEmail.subject"
                class="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div class="border rounded-md p-4 bg-ink-gray-1 overflow-auto max-h-64">
              <div class="prose prose-sm w-full" style="max-width: 100%;" v-html="generatedEmail.content"></div>
            </div>
          </div>
          <div class="border-t pt-4 mt-2">
            <Button
              :label="__('Generate Another')"
              variant="ghost"
              @click="generatedEmail = null"
            />
          </div>
        </div>
        <div v-else>
          <div class="mb-4">
            <FormControl
              type="select"
              v-model="tone"
              :label="__('Tone')"
              :options="[
                { label: __('Professional'), value: 'professional' },
                { label: __('Friendly'), value: 'friendly' },
                { label: __('Formal'), value: 'formal' },
                { label: __('Persuasive'), value: 'persuasive' },
              ]"
            />
          </div>
          <div class="mb-4">
            <FormControl
              type="textarea"
              v-model="additionalContext"
              :label="__('Additional Context (Optional)')"
              :placeholder="__('Any specific points to include or details about the lead...')"
              :rows="3"
            />
          </div>
          <div class="flex justify-end">
            <Button
              :label="__('Generate Email')"
              variant="solid"
              @click="generateEmail"
            />
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Dialog, FormControl, Button, createResource } from 'frappe-ui'
import { createToast } from '@/utils'
import { capture } from '@/telemetry'

const props = defineProps({
  lead: {
    type: Object,
    required: true,
  },
})

const show = defineModel()
const emit = defineEmits(['apply'])

const tone = ref('professional')
const additionalContext = ref('')
const loading = ref(false)
const error = ref(null)
const generatedEmail = ref(null)
const testEmailLoading = ref(false)

async function generateEmail() {
  loading.value = true
  error.value = null
  
  try {
    const response = await generateEmailContent.submit({
      lead_name: props.lead.name,
      tone: tone.value,
      additional_context: additionalContext.value
    })
    
    if (response.success) {
      generatedEmail.value = {
        subject: response.subject,
        content: response.content
      }
      capture('ai_email_generated', { tone: tone.value })
    } else {
      error.value = response.message || __('Unknown error occurred')
    }
  } catch (err) {
    console.error('Error generating email:', err)
    error.value = err.message || __('Error generating email')
  } finally {
    loading.value = false
  }
}

function useGeneratedEmail() {
  if (!generatedEmail.value) return
  
  emit('apply', {
    subject: generatedEmail.value.subject,
    content: generatedEmail.value.content
  })
  
  show.value = false
  capture('ai_generated_email_used', {})
}

async function sendTestEmail() {
  if (!generatedEmail.value) return
  
  testEmailLoading.value = true
  
  try {
    console.log("Sending to backend:", {
      lead_name: props.lead.name,
      subject: generatedEmail.value.subject,
      email_content: generatedEmail.value.content
    });
    
    const response = await sendTestEmailResource.submit({
      lead_name: props.lead.name,
      subject: generatedEmail.value.subject,
      email_content: generatedEmail.value.content
    })
    
    if (response.success) {
      createToast({
        title: __('Test Email Sent'),
        text: response.message,
        icon: 'check',
        iconClasses: 'text-ink-green-3'
      })
      capture('ai_test_email_sent', {})
    } else {
      createToast({
        title: __('Error'),
        text: response.message,
        icon: 'x',
        iconClasses: 'text-ink-red-4'
      })
    }
  } catch (err) {
    console.error('Error sending test email:', err)
    createToast({
      title: __('Error'),
      text: err.message || __('Could not send test email'),
      icon: 'x',
      iconClasses: 'text-ink-red-4'
    })
  } finally {
    testEmailLoading.value = false
  }
}

const generateEmailContent = createResource({
  url: 'crm.api.ai_email.generate_email_content',
  validate(values) {
    if (!values.lead_name) {
      return __('Lead is required')
    }
    return null
  }
})

const sendTestEmailResource = createResource({
  url: 'crm.api.ai_email.send_test_email',
  validate(values) {
    if (!values.lead_name) {
      return __('Lead is required')
    }
    if (!values.email_content) {
      return __('Email content is required')
    }
    if (!values.subject) {
      return __('Subject is required')
    }
    return null
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
</style> 