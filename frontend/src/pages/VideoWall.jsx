import React, { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'
import api from '../api.js'
import { Card, ErrorBanner, Spinner } from '../components/ui.jsx'

// MediaMTX's HLS port and ANPR_Standalone's own port are both exposed
// directly on the host (same convention as every other port in this stack)
// — the browser reaches them at window.location.hostname, not through the
// nginx /api proxy, since neither is a JSON API this app owns.
const HLS_PORT = 8888
const ANPR_PORT = 8090

function anprBase() {
  return `http://${window.location.hostname}:${ANPR_PORT}`
}

// Ported verbatim (logic unchanged) from ANPR_Standalone's own
// service/static/index.html demo page — orange = vehicle box, green = plate box.
function drawBoxes(ctx, events, scaleX, scaleY) {
  ctx.lineWidth = 2
  ctx.font = '14px system-ui'
  for (const e of events) {
    if (e.vehicle_bbox) {
      const [x1, y1, x2, y2] = e.vehicle_bbox
      ctx.strokeStyle = '#ff8c00'
      ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY)
      ctx.fillStyle = '#ff8c00'
      ctx.fillText(e.vehicle_class || 'vehicle', x1 * scaleX, y1 * scaleY - 6)
    }
    if (e.plate_bbox) {
      const [x1, y1, x2, y2] = e.plate_bbox
      ctx.strokeStyle = '#5ee0a0'
      ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY)
      ctx.fillStyle = '#5ee0a0'
      ctx.fillText(e.plate_no || '?', x1 * scaleX, y2 * scaleY + 16)
    }
  }
}

// The ANPR service is one CPU-only process shared by this one-shot demo
// endpoint AND every background camera it's currently tracking -- with a
// full real-world camera grid running, a plain request here can be starved
// for a long time (directly reproduced: 30+ seconds against 32 concurrent
// streams). fetch() has no timeout of its own, so without this the UI used
// to just sit on "Detecting..." forever with no error at all. Fail loudly
// and specifically instead.
const DETECT_TIMEOUT_MS = 20000

async function detectFrame(blob) {
  const form = new FormData()
  form.append('file', blob, 'frame.jpg')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), DETECT_TIMEOUT_MS)
  try {
    const res = await fetch(`${anprBase()}/detect/image`, { method: 'POST', body: form, signal: controller.signal })
    if (!res.ok) throw new Error(`ANPR service error ${res.status}`)
    return (await res.json()).events
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(
        `No response after ${DETECT_TIMEOUT_MS / 1000}s -- the ANPR service is likely busy `
        + 'processing live camera feeds right now. Try again in a moment.'
      )
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

// ---------------- Real camera tile (RTSP -> MediaMTX -> HLS) ----------------

function CameraTile({ feed }) {
  const videoRef = useRef(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    // A camera with its own ready-to-use hls_url (e.g. an external
    // provider's CDN-served .m3u8) is played directly; otherwise fall
    // back to assuming it's relayed through our own MediaMTX.
    const url = feed.hls_url || `http://${window.location.hostname}:${HLS_PORT}/${feed.stream_path}/index.m3u8`
    const video = videoRef.current
    let hls
    if (Hls.isSupported()) {
      hls = new Hls({ lowLatencyMode: true })
      hls.loadSource(url)
      hls.attachMedia(video)
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) setError('Feed unavailable — is the mock/live source running?')
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url
    } else {
      setError('HLS not supported in this browser')
    }
    return () => hls && hls.destroy()
  }, [feed.stream_path, feed.hls_url])

  return (
    <Card className="p-0 overflow-hidden">
      <div className="relative bg-black aspect-video">
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-contain" />
      </div>
      <div className="p-2 text-xs space-y-1">
        <div className="font-semibold">{feed.camera_id}</div>
        <div className="text-slate-500">{feed.district} · {feed.department}</div>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${
              feed.stream_status === 'connected'
                ? 'bg-green-500'
                : feed.stream_status === 'connecting'
                ? 'bg-amber-500 animate-pulse'
                : 'bg-slate-300'
            }`}
          />
          <span className="text-slate-400">
            {feed.stream_status === 'connected' && 'ANPR tracking — receiving frames'}
            {feed.stream_status === 'connecting' && 'ANPR tracking — reconnecting…'}
            {feed.stream_status === 'inactive' && 'ANPR tracking inactive'}
          </span>
        </div>
        {error && <div className="text-red-600">{error}</div>}
      </div>
    </Card>
  )
}

// ---------------- My Webcam tile (Live Demo Panel, source 1) ----------------

function WebcamTile() {
  const videoRef = useRef(null)
  const overlayRef = useRef(null)
  const captureCanvasRef = useRef(null)
  if (!captureCanvasRef.current) captureCanvasRef.current = document.createElement('canvas')
  const streamRef = useRef(null)
  const loopRef = useRef(null)
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('Idle.')
  const [lastPlate, setLastPlate] = useState(null)
  const [devices, setDevices] = useState([])
  const [selectedDeviceId, setSelectedDeviceId] = useState('')

  // Device labels are blank until getUserMedia has been granted at least
  // once (browser privacy) — call this again right after a successful
  // start() to pick up real labels, not just generic "Camera 1/2/...".
  async function refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      const all = await navigator.mediaDevices.enumerateDevices()
      const cams = all.filter((d) => d.kind === 'videoinput')
      setDevices(cams)
      setSelectedDeviceId((prev) => (prev && cams.some((c) => c.deviceId === prev) ? prev : cams[0]?.deviceId || ''))
    } catch {
      // enumerateDevices can fail in insecure contexts (non-localhost, non-https) — leave the list empty
    }
  }

  useEffect(() => {
    refreshDevices()
    const handler = () => refreshDevices()
    navigator.mediaDevices?.addEventListener?.('devicechange', handler)
    return () => navigator.mediaDevices?.removeEventListener?.('devicechange', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function startWithDevice(deviceId) {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (loopRef.current) clearTimeout(loopRef.current)

    // `ideal` (not `exact`) so the browser picks the closest resolution the
    // camera actually supports instead of failing outright — a low-end
    // webcam still works, it just won't get the extra detail. This matters
    // for reading a plate from any distance: the plate detector finds the
    // plate as a shape fine even in a low-res frame, but the OCR crop of
    // just that region only has as many real pixels as the capture
    // resolution gave it — upscaling that crop afterward can't invent
    // detail that was never captured.
    const videoConstraints = { width: { ideal: 1920 }, height: { ideal: 1080 } }
    if (deviceId) videoConstraints.deviceId = { exact: deviceId }

    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: videoConstraints })
    } catch (err) {
      setStatus('Could not access camera: ' + err.message)
      setRunning(false)
      return
    }
    const video = videoRef.current
    video.srcObject = streamRef.current
    await video.play()
    overlayRef.current.width = video.videoWidth
    overlayRef.current.height = video.videoHeight
    captureCanvasRef.current.width = video.videoWidth
    captureCanvasRef.current.height = video.videoHeight
    setRunning(true)
    setStatus('Running — sampling ~1 frame/sec.')
    refreshDevices() // now that permission is granted, labels become available
    loop()
  }

  function start() {
    startWithDevice(selectedDeviceId)
  }

  function stop() {
    if (loopRef.current) clearTimeout(loopRef.current)
    if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setRunning(false)
    setStatus('Stopped.')
    const ov = overlayRef.current
    if (ov) ov.getContext('2d').clearRect(0, 0, ov.width, ov.height)
  }

  function onDeviceChange(e) {
    const id = e.target.value
    setSelectedDeviceId(id)
    if (running) {
      setStatus('Switching camera…')
      startWithDevice(id) // hot-swap the source without a manual Stop/Start
    }
  }

  function loop() {
    if (!streamRef.current) return
    const cCanvas = captureCanvasRef.current
    cCanvas.getContext('2d').drawImage(videoRef.current, 0, 0, cCanvas.width, cCanvas.height)
    cCanvas.toBlob(async (blob) => {
      try {
        const events = await detectFrame(blob)
        const octx = overlayRef.current.getContext('2d')
        octx.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height)
        drawBoxes(octx, events, 1, 1)
        const plate = events.find((e) => e.plate_no)
        setLastPlate(plate ? plate.plate_no : null)
        setStatus(`Running — last check ${new Date().toLocaleTimeString()}, ${events.length} detection(s).`)
      } catch (err) {
        setStatus('Detect call failed: ' + err.message)
      }
      loopRef.current = setTimeout(loop, 1000)
    }, 'image/jpeg', 0.92) // higher quality now that capture resolution is higher — less compression loss on the extra detail
  }

  useEffect(() => () => stop(), [])

  return (
    <Card className="p-0 overflow-hidden ring-2 ring-purple-300">
      <div className="relative bg-black aspect-video">
        <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-contain" />
        <canvas ref={overlayRef} className="absolute inset-0 w-full h-full" />
      </div>
      <div className="p-2 text-xs space-y-1">
        <div className="font-semibold">My Webcam <span className="text-purple-600">· Live Demo</span></div>
        {devices.length > 0 && (
          <select
            value={selectedDeviceId}
            onChange={onDeviceChange}
            className="border border-slate-300 rounded px-1.5 py-1 text-xs w-full"
          >
            {devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        )}
        <div className="flex gap-2">
          <button
            onClick={start}
            disabled={running}
            className="px-2 py-1 bg-gujgov-700 text-white rounded disabled:opacity-40"
          >
            Start
          </button>
          <button
            onClick={stop}
            disabled={!running}
            className="px-2 py-1 bg-slate-200 rounded disabled:opacity-40"
          >
            Stop
          </button>
        </div>
        <div className="text-slate-500">{status}</div>
        {lastPlate && (
          <div className="text-green-600 font-semibold">Plate detected: {lastPlate}</div>
        )}
      </div>
    </Card>
  )
}

// ---------------- Upload Photo tile (Live Demo Panel, source 2) ----------------

function UploadTile() {
  const canvasRef = useRef(null)
  const imgRef = useRef(null)
  const [status, setStatus] = useState('Choose a photo of a vehicle or number plate.')
  const [busy, setBusy] = useState(false)
  const [hasImage, setHasImage] = useState(false)

  function onFile(e) {
    const file = e.target.files[0]
    if (!file) return
    const img = new Image()
    img.onload = () => {
      const canvas = canvasRef.current
      canvas.width = img.width
      canvas.height = img.height
      canvas.getContext('2d').drawImage(img, 0, 0)
      imgRef.current = img
      setHasImage(true)
      setStatus('Ready — click Detect.')
    }
    img.src = URL.createObjectURL(file)
  }

  function runDetect() {
    if (!imgRef.current) return
    setBusy(true)
    setStatus('Detecting...')
    const canvas = canvasRef.current
    canvas.toBlob(async (blob) => {
      try {
        const events = await detectFrame(blob)
        const ctx = canvas.getContext('2d')
        ctx.drawImage(imgRef.current, 0, 0)
        drawBoxes(ctx, events, 1, 1)
        setStatus(
          events.length
            ? `Found ${events.length} detection(s).`
            : 'No vehicle or plate detected in this image.'
        )
      } catch (err) {
        setStatus('Detect call failed: ' + err.message)
      }
      setBusy(false)
    }, 'image/jpeg', 0.92)
  }

  return (
    <Card className="p-0 overflow-hidden ring-2 ring-purple-300">
      <div className="relative bg-black aspect-video flex items-center justify-center">
        <canvas ref={canvasRef} className="max-w-full max-h-full" />
        {!hasImage && <span className="absolute text-slate-500 text-xs">No photo chosen</span>}
      </div>
      <div className="p-2 text-xs space-y-1">
        <div className="font-semibold">Upload Photo <span className="text-purple-600">· Live Demo</span></div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="file" accept="image/*" onChange={onFile} className="text-xs max-w-[140px]" />
          <button
            onClick={runDetect}
            disabled={!hasImage || busy}
            className="px-2 py-1 bg-gujgov-700 text-white rounded disabled:opacity-40"
          >
            Detect
          </button>
        </div>
        <div className="text-slate-500">{status}</div>
      </div>
    </Card>
  )
}

// ---------------- Live Grid / Demo Mode switch ----------------
//
// Background camera tracking (up to 30+ real cameras) and the one-shot
// webcam/upload demo panel share ONE CPU-only ANPR process -- running a
// full real grid can starve the demo panel badly enough to time out
// (confirmed directly against real Sentinel Grid load). Rather than let
// that show up as an unexplained hang, make the tradeoff an explicit
// choice: only one of the two runs background inference at a time.

function ModeGate({ active, message, children }) {
  if (active) return children
  return (
    <div className="relative">
      <div className="opacity-30 pointer-events-none">{children}</div>
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="bg-white/95 border border-slate-300 rounded px-3 py-2 text-xs text-slate-600 text-center shadow">
          {message}
        </div>
      </div>
    </div>
  )
}

function LiveGridSwitch({ running, pending, onToggle }) {
  const label = running === null ? 'Checking…' : running ? 'Live Grid' : 'Demo Mode'
  return (
    <div className="flex items-center gap-3 bg-white border border-slate-200 rounded px-3 py-2">
      <button
        type="button"
        role="switch"
        aria-checked={!!running}
        disabled={running === null || pending}
        onClick={onToggle}
        className={`relative w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${
          running ? 'bg-gujgov-700' : 'bg-slate-300'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
            running ? 'translate-x-5' : ''
          }`}
        />
      </button>
      <div className="text-sm">
        <div className="font-semibold">{label}</div>
        <div className="text-xs text-slate-500">
          {pending
            ? 'Switching…'
            : running
            ? 'Processing all registry cameras. Webcam/Upload panel is paused.'
            : 'Camera grid paused. Webcam/Upload panel has full CPU.'}
        </div>
      </div>
    </div>
  )
}

// ---------------- Unified grid ----------------

export default function VideoWall() {
  const [feeds, setFeeds] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [liveGridRunning, setLiveGridRunning] = useState(null) // null = not checked yet
  const [switching, setSwitching] = useState(false)

  useEffect(() => {
    api
      .get('/feeds')
      .then((res) => setFeeds(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Failed to load feeds'))
      .finally(() => setLoading(false))
    refreshLiveGridStatus()
  }, [])

  function refreshLiveGridStatus() {
    api
      .get('/feeds/live-grid/status')
      .then((res) => setLiveGridRunning(res.data.running))
      .catch(() => {}) // leave as "checking" rather than guessing
  }

  async function toggleLiveGrid() {
    setSwitching(true)
    try {
      if (liveGridRunning) {
        await api.post('/feeds/live-grid/stop')
        setLiveGridRunning(false)
      } else {
        await api.post('/feeds/live-grid/start')
        // Starting a full grid is staggered server-side and takes real
        // time (~1.5s per camera) -- reflect "on" immediately (the
        // switch itself did succeed), individual tile status will catch
        // up as streams actually connect.
        setLiveGridRunning(true)
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to switch live grid mode')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="space-y-3">
      <ErrorBanner message={error} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-500">
          {feeds.length} analytics-capable camera{feeds.length === 1 ? '' : 's'} from Model 1's registry, plus
          the live ANPR demo panel (webcam / photo upload) below. Only one runs background detection at a time.
        </div>
        <LiveGridSwitch running={liveGridRunning} pending={switching} onToggle={toggleLiveGrid} />
      </div>
      {loading ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {feeds.map((f) => (
            <ModeGate
              key={f.camera_id}
              active={liveGridRunning !== false}
              message="Live Grid is paused (Demo Mode active) — switch back to view cameras."
            >
              <CameraTile feed={f} />
            </ModeGate>
          ))}
          <ModeGate
            active={liveGridRunning !== true}
            message="Switch to Demo Mode to use your webcam here."
          >
            <WebcamTile />
          </ModeGate>
          <ModeGate
            active={liveGridRunning !== true}
            message="Switch to Demo Mode to upload a photo here."
          >
            <UploadTile />
          </ModeGate>
        </div>
      )}
    </div>
  )
}
