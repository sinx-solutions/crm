import { io } from 'socket.io-client'
import { getCachedListResource } from 'frappe-ui/src/resources/listResource'
import { getCachedResource } from 'frappe-ui/src/resources/resources'

// Fixed socketio port - Frappe usually uses port 9000 for websockets
const SOCKETIO_PORT = 9000
const SOCKET_RECONNECT_MAX = 5 // Maximum number of times to try reconnecting

// Variable to track socket connection state
let isSocketConnected = false
let reconnectAttempts = 0
let socket = null

export function initSocket() {
  // If we already have a connected socket, return it
  if (socket && isSocketConnected) {
    return socket
  }
  
  let host = window.location.hostname
  let siteName = window.site_name || 'newcrm.localhost'  // Default to newcrm.localhost if not set
  
  // Always use the fixed socketio port for development environment
  let port = `:${SOCKETIO_PORT}`
  let protocol = 'http'  // Use http for development
  
  let url = `${protocol}://${host}${port}/${siteName}`
  
  console.log(`Connecting to socket at: ${url}`)
  
  // Clean up any existing socket
  if (socket) {
    try {
      socket.disconnect()
    } catch (e) {
      console.warn('Error disconnecting existing socket:', e)
    }
  }
  
  // Create new socket
  socket = io(url, {
    withCredentials: true,
    reconnectionAttempts: 10,  // More reconnection attempts
    reconnectionDelay: 1000,   // Start with 1s delay
    reconnectionDelayMax: 5000, // Max 5s delay
    timeout: 10000             // Longer timeout
  })
  
  // Add better connection event handlers
  socket.on('connect', () => {
    console.log('Socket connected successfully!')
    isSocketConnected = true
    reconnectAttempts = 0
    
    // Add a heartbeat to keep connection alive
    startHeartbeat()
  })
  
  socket.on('connect_error', (err) => {
    console.error('Socket connection error:', err.message)
    isSocketConnected = false
    
    // Increment reconnect attempts counter
    reconnectAttempts++
    
    // If we've tried too many times, stop trying to reconnect automatically
    if (reconnectAttempts >= SOCKET_RECONNECT_MAX) {
      console.warn(`Reached maximum reconnect attempts (${SOCKET_RECONNECT_MAX}). Stopping automatic reconnection.`)
    }
  })
  
  socket.on('disconnect', (reason) => {
    console.warn('Socket disconnected:', reason)
    isSocketConnected = false
    stopHeartbeat()
  })
  
  socket.on('reconnect', (attemptNumber) => {
    console.log(`Socket reconnected after ${attemptNumber} attempts`)
    isSocketConnected = true
    reconnectAttempts = 0
  })
  
  socket.on('refetch_resource', (data) => {
    console.log('Received refetch_resource event:', data)
    if (data.cache_key) {
      let resource =
        getCachedResource(data.cache_key) ||
        getCachedListResource(data.cache_key)
      if (resource) {
        resource.reload()
      }
    }
  })
  
  return socket
}

// Helper function to check if socket is connected
export function isConnected() {
  return isSocketConnected
}

// Helper function to get the existing socket
export function getSocket() {
  return socket
}

// Helper function to manually reconnect
export function reconnect() {
  console.log('Manually reconnecting to socket...')
  return initSocket()
}

// Heartbeat to keep connection alive
let heartbeatInterval = null

function startHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
  }
  
  // Send a heartbeat every 30 seconds
  heartbeatInterval = setInterval(() => {
    if (socket && isSocketConnected) {
      socket.emit('heartbeat', { timestamp: Date.now() })
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
    heartbeatInterval = null
  }
}