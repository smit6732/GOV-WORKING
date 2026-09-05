import { useEffect, useRef, useState } from 'react'

/** Reconnecting WebSocket to /api/ws/alerts, tunneling through the same
 * nginx/vite proxy every other request already goes through. Auth is a
 * short-lived JWT already in localStorage, passed as a query param since
 * the browser WebSocket API can't set an Authorization header. */
export default function useAlertsSocket() {
  const [alerts, setAlerts] = useState([])
  const [connected, setConnected] = useState(false)
  const retryRef = useRef(1000)

  useEffect(() => {
    let socket
    let closedByEffect = false
    let retryTimer

    function connect() {
      const token = localStorage.getItem('token')
      if (!token) return
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${protocol}://${window.location.host}/api/ws/alerts?token=${encodeURIComponent(token)}`)

      socket.onopen = () => {
        setConnected(true)
        retryRef.current = 1000
      }
      socket.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data)
          setAlerts((prev) => [payload, ...prev].slice(0, 50))
        } catch {
          // ignore malformed frames
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (closedByEffect) return
        retryTimer = setTimeout(connect, retryRef.current)
        retryRef.current = Math.min(retryRef.current * 2, 15000)
      }
      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      closedByEffect = true
      clearTimeout(retryTimer)
      if (socket) socket.close()
    }
  }, [])

  return { alerts, connected }
}
