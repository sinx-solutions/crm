<template>
  <div class="flex justify-between gap-3 border-t px-4 py-2.5 sm:px-10">
    <div class="flex gap-1.5">
      <Button
        ref="sendEmailRef"
        variant="ghost"
        :class="[
          showEmailBox ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : '',
        ]"
        :label="__('Reply')"
        @click="toggleEmailBox()"
      >
        <template #prefix>
          <Email2Icon class="h-4" />
        </template>
      </Button>
      <Button
        variant="ghost"
        :label="__('Comment')"
        :class="[
          showCommentBox ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : '',
        ]"
        @click="toggleCommentBox()"
      >
        <template #prefix>
          <CommentIcon class="h-4" />
        </template>
      </Button>
    </div>
  </div>
  <div
    v-show="showEmailBox"
    @keydown.ctrl.enter.capture.stop="submitEmail"
    @keydown.meta.enter.capture.stop="submitEmail"
  >
    <EmailEditor
      ref="newEmailEditor"
      v-model:content="newEmail"
      :submitButtonProps="{
        variant: 'solid',
        onClick: submitEmail,
        disabled: emailEmpty,
      }"
      :discardButtonProps="{
        onClick: () => {
          showEmailBox = false
          newEmailEditor.subject = subject
          newEmailEditor.toEmails = doc.data.email ? [doc.data.email] : []
          newEmailEditor.ccEmails = []
          newEmailEditor.bccEmails = []
          newEmailEditor.cc = false
          newEmailEditor.bcc = false
          newEmail = ''
        },
      }"
      :editable="showEmailBox"
      v-model="doc.data"
      v-model:attachments="attachments"
      :doctype="doctype"
      :subject="subject"
      :placeholder="
        __('Hi John, \n\nCan you please provide more details on this...')
      "
    />
  </div>
  <div v-show="showCommentBox">
    <CommentBox
      ref="newCommentEditor"
      v-model:content="newComment"
      :submitButtonProps="{
        variant: 'solid',
        onClick: submitComment,
        disabled: commentEmpty,
      }"
      :discardButtonProps="{
        onClick: () => {
          showCommentBox = false
          newComment = ''
        },
      }"
      :editable="showCommentBox"
      v-model="doc.data"
      v-model:attachments="attachments"
      :doctype="doctype"
      :placeholder="__('@John, can you please check this?')"
    />
  </div>
</template>

<script setup>
import EmailEditor from '@/components/EmailEditor.vue'
import CommentBox from '@/components/CommentBox.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import { capture } from '../telemetry'
import { usersStore } from '@/stores/users'
import { useStorage } from '@vueuse/core'
import { call, createResource } from 'frappe-ui'
import { useOnboarding } from 'frappe-ui/frappe'
import { ref, watch, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { __ } from '../utils/translations'
import { globalStore } from '@/stores/global'
import { validateEmail } from '@/utils'

const props = defineProps({
  doctype: {
    type: String,
    default: 'CRM Lead',
  },
})

const loading = ref(false)

// Get socket from globalStore
const { $socket } = globalStore()

const doc = defineModel()
const reload = defineModel('reload')

const emit = defineEmits(['scroll'])

const { getUser } = usersStore()
const { updateOnboardingStep } = useOnboarding('frappecrm')

const showEmailBox = ref(false)
const showCommentBox = ref(false)
const newEmail = useStorage('emailBoxContent', '')
const newComment = useStorage('commentBoxContent', '')
const newEmailEditor = ref(null)
const newCommentEditor = ref(null)
const sendEmailRef = ref(null)
const attachments = ref([])

const subject = computed(() => {
  let prefix = ''
  if (doc.value.data?.lead_name) {
    prefix = doc.value.data.lead_name
  } else if (doc.value.data?.organization) {
    prefix = doc.value.data.organization
  }
  
  if (prefix) {
    return `${prefix} (#${doc.value.data.name})`
  } else {
    return `Regarding Lead #${doc.value.data.name}`
  }
})

const signature = createResource({
  url: 'crm.api.get_user_signature',
  cache: 'user-email-signature',
  auto: true,
})

function setSignature(editor) {
  if (!signature.data) return
  signature.data = signature.data.replace(/\\n/g, '<br>')
  let emailContent = editor.getHTML()
  emailContent = emailContent.startsWith('<p></p>')
    ? emailContent.slice(7)
    : emailContent
  editor.commands.setContent(signature.data + emailContent)
  editor.commands.focus('start')
}

watch(
  () => showEmailBox.value,
  (value) => {
    if (value) {
      let editor = newEmailEditor.value.editor
      editor.commands.focus()
      setSignature(editor)
    }
  },
)

watch(
  () => showCommentBox.value,
  (value) => {
    if (value) {
      newCommentEditor.value.editor.commands.focus()
    }
  },
)

const commentEmpty = computed(() => {
  return !newComment.value || newComment.value === '<p></p>'
})

const emailEmpty = computed(() => {
  return (
    !newEmail.value ||
    newEmail.value === '<p></p>' ||
    !newEmailEditor.value?.toEmails?.length
  )
})

// ADDED: Basic email validation function
function isValidEmailFormat(email) {
  if (!email || typeof email !== 'string') return false;
  return validateEmail(email);
}

function validateEmailsBeforeSend() {
  const toEmailsList = newEmailEditor.value?.toEmails || [];
  if (!toEmailsList.length) {
    console.error('[CommunicationArea] Validation Error: No recipients in TO field.');
    return false;
  }

  const allEmailGroups = {
    to: toEmailsList,
    cc: newEmailEditor.value?.ccEmails || [],
    bcc: newEmailEditor.value?.bccEmails || [],
  };

  for (const groupName in allEmailGroups) {
    const emailArray = allEmailGroups[groupName];
    for (const item of emailArray) {
      let emailId = null;
      if (typeof item === 'string') {
        emailId = item;
      } else if (item && typeof item.id === 'string') {
        emailId = item.id;
      }

      if (!emailId || !emailId.trim()) {
        // If it\'s an empty/null/undefined emailId
        if (groupName === 'to') {
          // TO field cannot have empty entries if the array itself is not empty
          console.error(`[CommunicationArea] Validation Error: Empty or invalid email entry in TO field.`);
          return false;
        }
        // For CC/BCC, an empty entry might be permissible, so we continue
        console.warn(`[CommunicationArea] Validation Warning: Empty email entry in ${groupName.toUpperCase()} field.`);
        continue; 
      }

      if (!isValidEmailFormat(emailId)) {
        console.error(`[CommunicationArea] Validation Error: Invalid email format in ${groupName.toUpperCase()} field - ${emailId}`);
        return false;
      }
    }
  }
  return true;
}

async function sendEmail() {
  console.log('==== EMAIL PROCESS STARTING ====', newEmailEditor.value);
  if (!validateEmailsBeforeSend()) { 
    console.error('[CommunicationArea] Email validation failed. Aborting send.');
    return; 
  }

  loading.value = true;
  console.log('[CommunicationArea] Email validation passed.');
  
  // Extract data from the EmailEditor component
  const editorRef = newEmailEditor.value;
  const recipientsList = editorRef?.toEmails?.map(e => typeof e === 'string' ? e : e.id) || [];
  const ccList = editorRef?.ccEmails?.map(e => typeof e === 'string' ? e : e.id) || [];
  const bccList = editorRef?.bccEmails?.map(e => typeof e === 'string' ? e : e.id) || [];
  const emailSubject = editorRef?.subject.value || subject.value; // Use subject from editor ref if available
  const emailContent = editorRef?.content.value || newEmail.value; // Use content from editor ref if available
  const templateName = editorRef?.selectedTemplateName.value; // Get selected template name
  const isAI = editorRef?.isAIGenerated.value; // Check if AI was used

  const emailDetails = {
    recipients: recipientsList,
    cc: ccList,
    bcc: bccList,
    subject: emailSubject,
    content: emailContent, // Content from the editor
    selected_template_name: templateName, // Pass the selected template name
    doctype: props.doctype,
    name: doc.value.data.name,
    // attachments: attachments.value, // Add attachment handling if needed
  };

  console.log('[CommunicationArea] Preparing to call send_ai_email API with details:', emailDetails);
  
  try {
    const response = await call('crm.api.ai_email.send_ai_email', emailDetails);
    console.log('[CommunicationArea] API response:', response);

    if (response.success) {
      capture('email_sent', { ai_generated: isAI, template_used: !!templateName });
      newEmail.value = ''; // Clear editor content
      showEmailBox.value = false;
      reload.value = true;
      console.log('[CommunicationArea] Refreshing document to show email in timeline');
      nextTick(() => emit('scroll'));
      updateOnboardingStep('compose-email', 'complete');
      console.log('==== EMAIL PROCESS COMPLETED SUCCESSFULLY ====');
    } else {
      console.error('[CommunicationArea] Error sending email:', response.message);
      // TODO: Show error toast to user based on response.message
      alert(`Error sending email: ${response.message || 'Unknown server error'}`);
    }
  } catch (error) {
    console.error('[CommunicationArea] Exception during sendEmail API call:', error);
    // TODO: Show error toast to user
    alert(`Error sending email: ${error.message || 'Client-side error'}`);
  } finally {
    loading.value = false;
  }
}

async function sendComment() {
  let comment = await call('frappe.desk.form.utils.add_comment', {
    reference_doctype: props.doctype,
    reference_name: doc.value.data.name,
    content: newComment.value,
    comment_email: getUser().email,
    comment_by: getUser()?.full_name || undefined,
  })
  if (comment && attachments.value.length) {
    capture('comment_attachments_added')
    await call('crm.api.comment.add_attachments', {
      name: comment.name,
      attachments: attachments.value.map((x) => x.name),
    })
  }
}

function submitEmail() {
  sendEmail();
}

async function submitComment() {
  if (commentEmpty.value) return
  showCommentBox.value = false
  await sendComment()
  newComment.value = ''
  reload.value = true
  emit('scroll')
  capture('comment_sent', { doctype: props.doctype })
  updateOnboardingStep('add_first_comment')
}

function toggleEmailBox() {
  if (showCommentBox.value) {
    showCommentBox.value = false
  }
  showEmailBox.value = !showEmailBox.value
}

function toggleCommentBox() {
  if (showEmailBox.value) {
    showEmailBox.value = false
  }
  showCommentBox.value = !showCommentBox.value
}

onMounted(() => {
  // Set up a socket listener to refresh the timeline when a bulk email completes
  $socket.on('crm:refresh_timeline', (data) => {
    if (data.doctype === props.doctype && data.name === doc.value.data.name) {
      console.log("Received timeline refresh event for", data.name)
      // First clear the reload flag to force reactivity
      reload.value = false
      
      // Add a small delay before refreshing
      setTimeout(() => {
        reload.value = true
        
        // Scroll to show the newly added content
        setTimeout(() => {
          emit('scroll')
          console.log("Scrolled to latest content (from socket event)")
        }, 300)
      }, 200)
    }
  })
})

onBeforeUnmount(() => {
  // Clean up the socket listener
  $socket.off('crm:refresh_timeline')
})

defineExpose({
  show: showEmailBox,
  showComment: showCommentBox,
  editor: newEmailEditor,
})
</script>
