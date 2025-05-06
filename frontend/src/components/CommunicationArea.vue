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
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { __ } from '../utils/translations'
import { globalStore } from '@/stores/global'

const props = defineProps({
  doctype: {
    type: String,
    default: 'CRM Lead',
  },
})

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
  signature.data = signature.data.replace(/\n/g, '<br>')
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

async function sendMail() {
  console.log("==== EMAIL PROCESS STARTING ====");
  let recipients = newEmailEditor.value.toEmails
  let subject = newEmailEditor.value.subject
  let cc = newEmailEditor.value.ccEmails || []
  let bcc = newEmailEditor.value.bccEmails || []

  console.log("Email details:", {
    recipients,
    subject,
    doctype: props.doctype,
    name: doc.value.data.name,
    hasAttachments: attachments.value.length > 0
  });

  if (attachments.value.length) {
    capture('email_attachments_added')
  }

  try {
    console.log("Calling send_ai_email API...");
    // Use the API which will now always use Frappe's email system
    const response = await call('crm.api.ai_email.send_ai_email', {
      recipients: recipients.join(', '),
      cc: cc.join(', '),
      bcc: bcc.join(', '),
      subject: subject,
      content: newEmail.value,
      doctype: props.doctype,
      name: doc.value.data.name
    });
    
    console.log("API response:", response);
    
    // Log analytics
    if (newEmailEditor.value?.isAIGenerated) {
      capture('ai_email_sent', { doctype: props.doctype });
    } else {
      capture('email_sent', { doctype: props.doctype });
    }
    
    // Trigger a refresh of the document to show the new email in timeline
    console.log("Refreshing document to show email in timeline");
    
    // First clear the reload flag to force reactivity
    reload.value = false;
    
    // Wait a bit for the email to be fully processed
    setTimeout(async () => {
      try {
        // Trigger a complete document reload using Frappe's reload_docinfo
        console.log("Reload document info");
        await call('frappe.desk.form.load.get_docinfo', {
          doctype: props.doctype,
          name: doc.value.data.name
        });
        
        console.log("Setting reload flag");
        reload.value = true;
        
        // Scroll to show the newly added email
        setTimeout(() => {
          emit('scroll');
          console.log("Scrolled to latest content");
        }, 300);
      } catch (error) {
        console.error("Error refreshing doc info:", error);
        // Still try to refresh the UI even if API call failed
        reload.value = true;
      }
    }, 1000);
    
    // Update onboarding step if applicable
    updateOnboardingStep('send_first_email');
    
    console.log("==== EMAIL PROCESS COMPLETED SUCCESSFULLY ====");
    return true;
  } catch (error) {
    console.error("Error sending email:", error);
    console.log("==== EMAIL PROCESS FAILED ====");
    return false;
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

async function submitEmail() {
  if (emailEmpty.value) return
  showEmailBox.value = false
  
  // Try to send the email
  const success = await sendMail()
  
  if (success) {
    // Reset the email form only if sent successfully
    newEmail.value = ''
    
    // Clear the email editor content and reset fields
    if (newEmailEditor.value) {
      newEmailEditor.value.subject = subject.value
      newEmailEditor.value.toEmails = doc.value.data.email ? [doc.value.data.email] : []
      newEmailEditor.value.ccEmails = []
      newEmailEditor.value.bccEmails = []
      newEmailEditor.value.cc = false
      newEmailEditor.value.bcc = false
      newEmailEditor.value.isAIGenerated = false
    }
    
    attachments.value = []
  } else {
    // If there was an error, show the email box again
    showEmailBox.value = true
  }
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
