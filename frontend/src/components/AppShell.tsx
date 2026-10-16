import type { ReactNode } from 'react';
import {
  Activity, ArrowUpRight, Building2, ChevronDown, CircleHelp, Command, FileBarChart, FlaskConical,
  Camera, LayoutDashboard, Leaf, Settings2, ShieldCheck,
  Siren, Sparkles, Waves,
} from 'lucide-react';
import type { NavKey, SystemHealth } from '../types';
import { HealthTag } from './StatusPill';

const navItems: { key: NavKey; label: string; icon: typeof LayoutDashboard; group: string }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'Workspace' },
  { key: 'twin', label: 'Campus twin', icon: Building2, group: 'Workspace' },
  { key: 'camera', label: 'Camera & video', icon: Camera, group: 'Workspace' },
  { key: 'events', label: 'Live events', icon: Siren, group: 'Workspace' },
  { key: 'actions', label: 'Actions & audit', icon: ShieldCheck, group: 'Operations' },
  { key: 'copilot', label: 'Sustainability copilot', icon: Sparkles, group: 'Intelligence' },
  { key: 'whatif', label: 'What-if lab', icon: FlaskConical, group: 'Intelligence' },
  { key: 'reports', label: 'Reports & impact', icon: FileBarChart, group: 'Insights' },
  { key: 'settings', label: 'Settings & assumptions', icon: Settings2, group: 'System' },
];

interface Props {
  active: NavKey;
  setActive: (key: NavKey) => void;
  health?: SystemHealth;
  demoMode: boolean;
  connectionLabel: string;
  onRefresh: () => void;
  onHelp: () => void;
  children: ReactNode;
}

export function AppShell({ active, setActive, health, demoMode, connectionLabel, onRefresh, onHelp, children }: Props) {
  return <div className="app-frame">
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><Leaf size={21} strokeWidth={2.4} /></div>
        <div><div className="brand-name">campustwin<span>ai</span></div><div className="brand-caption">SUSTAINABILITY OPS</div></div>
      </div>
      <div className="campus-selector">
        <div className="campus-avatar"><Building2 size={16} /></div>
        <div className="campus-copy"><strong>North Campus</strong><span>Operations workspace</span></div>
        <ChevronDown size={15} className="muted-icon" />
      </div>
      <nav className="primary-nav" aria-label="Main navigation">
        {['Workspace', 'Operations', 'Intelligence', 'Insights', 'System'].map((group) => <div className="nav-group" key={group}>
          <div className="nav-label">{group}</div>
          {navItems.filter((item) => item.group === group).map(({ key, label, icon: Icon }) => <button key={key} className={`nav-item ${active === key ? 'active' : ''}`} onClick={() => setActive(key)}>
            <Icon size={17} strokeWidth={1.9} /><span>{label}</span>
            {key === 'events' && health && <span className="nav-live-dot" aria-label="Live event feed" />}
          </button>)}
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-help">
          <div className="help-icon"><CircleHelp size={16} /></div>
          <div><strong>Need a hand?</strong><span>See the demo flow</span></div>
          <button className="mini-arrow" onClick={onHelp} aria-label="Open demo guide"><ArrowUpRight size={15} /></button>
        </div>
        <div className="operator-card">
          <div className="operator-avatar">OP</div>
          <div><strong>Campus operator</strong><span>Local workspace</span></div>
        </div>
      </div>
    </aside>

    <div className="main-column">
      <header className="topbar">
        <div className="breadcrumbs"><span>CampusTwin AI</span><span className="crumb-slash">/</span><strong>{navItems.find((item) => item.key === active)?.label || 'Overview'}</strong></div>
        <div className="topbar-actions">
          <div className={`connection-chip ${connectionLabel === 'Connected' ? 'is-connected' : connectionLabel === 'Demo simulation' ? 'is-demo' : 'is-offline'}`}>
            <span className="connection-dot" />{connectionLabel}
          </div>
          <button className="icon-button refresh-button" onClick={onRefresh} title="Refresh data" aria-label="Refresh data"><Activity size={17} /></button>
          <button className="icon-button" onClick={onHelp} title="Help and demo guide" aria-label="Help"><CircleHelp size={17} /></button>
          <div className="topbar-divider" />
          <button className="profile-button" aria-label="Current operator"><span className="profile-initials">CO</span><span className="profile-role">Operator</span><ChevronDown size={14} /></button>
        </div>
      </header>

      <main className="main-content">
        {demoMode && <div className="demo-ribbon"><span className="demo-pulse" /> <strong>LOCAL DEMO SIMULATION</strong><span>Every reading is synthetic. Actions do not control physical devices.</span><span className="ribbon-spacer" /><Waves size={14} /> Offline-ready preview</div>}
        {health && <div className="health-strip">
          <span className="health-strip-label"><Activity size={14} /> SYSTEM HEALTH</span>
          <span className="health-item">API <HealthTag value={health.backend.state} /></span>
          <span className="health-item">Database <HealthTag value={health.database.state} /></span>
          <span className="health-item">Camera <HealthTag value={health.camera.state} /></span>
          <span className="health-item">Sensor feed <HealthTag value={health.sensorFeed.state} /></span>
          <span className="health-item health-ai">Copilot <HealthTag value={health.copilot.state} /></span>
          <span className="health-strip-end"><span className="small-live-dot" /> {health.scenarioClock.mode === 'ACCELERATED' ? `${health.scenarioClock.multiplier ?? '—'}× scenario clock` : health.scenarioClock.mode === 'REAL_TIME' ? 'Real-time clock' : 'Clock unknown'}</span>
        </div>}
        {children}
      </main>
      <footer className="app-footer"><span><Leaf size={13} /> CampusTwin AI</span><span>Evidence before impact.</span><span><Command size={12} /> Local-first operations workspace</span></footer>
    </div>
  </div>;
}
