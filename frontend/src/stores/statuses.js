import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import { capture } from '@/telemetry'
import { parseColor } from '@/utils'
import { defineStore } from 'pinia'
import { createListResource } from 'frappe-ui'
import { reactive, h } from 'vue'

export const statusesStore = defineStore('crm-statuses', () => {
  let leadStatusesByName = reactive({})
  let dealStatusesByName = reactive({})
  let communicationStatusesByName = reactive({})

  const leadStatuses = createListResource({
    doctype: 'CRM Lead Status',
    fields: ['name', 'color', 'position'],
    orderBy: 'position asc',
    cache: 'lead-statuses',
    initialData: [],
    auto: true,
    transform(statuses) {
      for (let status of statuses) {
        status.color = parseColor(status.color)
        leadStatusesByName[status.name] = status
      }
      return statuses
    },
  })

  const dealStatuses = createListResource({
    doctype: 'CRM Deal Status',
    fields: ['name', 'color', 'position'],
    orderBy: 'position asc',
    cache: 'deal-statuses',
    initialData: [],
    auto: true,
    transform(statuses) {
      for (let status of statuses) {
        status.color = parseColor(status.color)
        dealStatusesByName[status.name] = status
      }
      return statuses
    },
  })

  const communicationStatuses = createListResource({
    doctype: 'CRM Communication Status',
    fields: ['name'],
    cache: 'communication-statuses',
    initialData: [],
    auto: true,
    transform(statuses) {
      for (let status of statuses) {
        communicationStatusesByName[status.name] = status
      }
      return statuses
    },
  })

  function getLeadStatus(name) {
    if (!name) {
      if (leadStatuses.data && leadStatuses.data.length > 0) {
        name = leadStatuses.data[0].name;
      } else {
        return { name: 'New', color: 'text-ink-gray-4' };
      }
    }
    return leadStatusesByName[name] || { name: name, color: 'text-ink-gray-4' };
  }

  function getDealStatus(name) {
    if (!name) {
      if (dealStatuses.data && dealStatuses.data.length > 0) {
        name = dealStatuses.data[0].name;
      } else {
        return { name: 'Open', color: 'text-ink-gray-4' };
      }
    }
    return dealStatusesByName[name] || { name: name, color: 'text-ink-gray-4' };
  }

  function getCommunicationStatus(name) {
    if (!name) {
      if (communicationStatuses.data && communicationStatuses.data.length > 0) {
        name = communicationStatuses.data[0].name;
      } else {
        return { name: 'New' };
      }
    }
    return communicationStatusesByName[name] || { name: name };
  }

  function statusOptions(doctype, action, statuses = []) {
    let statusesByName =
      doctype == 'deal' ? dealStatusesByName : leadStatusesByName

    if (statuses.length) {
      statusesByName = statuses.reduce((acc, status) => {
        acc[status] = statusesByName[status]
        return acc
      }, {})
    }

    let options = []
    for (const status in statusesByName) {
      options.push({
        label: statusesByName[status]?.name,
        value: statusesByName[status]?.name,
        icon: () => h(IndicatorIcon, { class: statusesByName[status]?.color }),
        onClick: () => {
          capture('status_changed', { doctype, status })
          action && action('status', statusesByName[status]?.name)
        },
      })
    }
    return options
  }

  return {
    leadStatuses,
    dealStatuses,
    communicationStatuses,
    getLeadStatus,
    getDealStatus,
    getCommunicationStatus,
    statusOptions,
  }
})
