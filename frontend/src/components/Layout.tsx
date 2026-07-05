import { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, ListTree, Activity, Server, ActivitySquare } from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <ActivitySquare className="text-primary" size={28} style={{ color: 'var(--primary-color)' }} />
          <span className="text-gradient">DistriJob</span>
        </div>
        
        <nav className="flex flex-col gap-2 mt-4">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <LayoutDashboard size={20} />
            Dashboard
          </NavLink>
          <NavLink to="/queues" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <ListTree size={20} />
            Queues
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Activity size={20} />
            Job Explorer
          </NavLink>
          <NavLink to="/workers" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Server size={20} />
            Workers
          </NavLink>
        </nav>
      </aside>

      <main className="main-content">
        <div className="container">
          {children}
        </div>
      </main>
    </div>
  );
}
