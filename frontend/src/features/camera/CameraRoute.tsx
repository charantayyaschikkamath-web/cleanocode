import { useState } from 'react';
import { Camera, ShieldCheck, Video } from 'lucide-react';
import CameraPanel from './CameraPanel';

const visionApiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export function CameraRoute() {
  const [roomId, setRoomId] = useState('CS-LAB-01');
  const [appliedRoomId, setAppliedRoomId] = useState('CS-LAB-01');

  return <div className="page-stack ct-camera-route">
    <div className="page-header">
      <div>
        <div className="eyebrow">LOCAL VISION · EVIDENCE FIRST</div>
        <h1>Camera & video analysis</h1>
        <p>Connect a webcam/USB camera or analyze a saved campus recording. Only person presence is detected; no identity or face recognition.</p>
      </div>
      <div className="page-header-actions"><span className="helper-note"><ShieldCheck size={14} /> Privacy-first processing</span></div>
    </div>
    <section className="panel ct-camera-room-select">
      <label htmlFor="ct-active-room-id"><Camera size={16} /> Room / zone ID</label>
      <input id="ct-active-room-id" value={roomId} onChange={(event) => setRoomId(event.target.value)} maxLength={120} placeholder="e.g. CS-LAB-01" />
      <button className="button button-primary" type="button" disabled={!roomId.trim()} onClick={() => setAppliedRoomId(roomId.trim())}>Use this room</button>
      <span>Evidence will be tagged to <strong>{appliedRoomId}</strong>. Use an ID that matches your room registry when connected to campus data.</span>
    </section>
    <div className="ct-camera-mode-note"><Video size={17} /><span><strong>Two input paths.</strong> Live camera uses your connected device. Video analysis reads the selected recording inside the browser and sends only sampled JPEG frames to the local inference endpoint.</span></div>
    <CameraPanel roomId={appliedRoomId} apiBaseUrl={visionApiBase} />
  </div>;
}
