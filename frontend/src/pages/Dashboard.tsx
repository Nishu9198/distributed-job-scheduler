import { useEffect, useState } from 'react';
import { Activity, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import { getQueues, getWorkers } from '../api';

export default function Dashboard() {
  const [queues, setQueues] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getQueues().catch(() => ({ items: [] })),
      getWorkers().catch(() => ({ items: [] }))
    ]).then(([qData, wData]) => {
      setQueues(qData.items || []);
      setWorkers(wData.items || []);
      setLoading(false);
    });
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">System Overview</h1>
      
      <div className="grid grid-cols-4 gap-6 mb-8">
        <div className="glass-panel glass-panel-hover flex flex-col gap-2">
          <div className="flex items-center justify-between text-muted">
            <span className="text-sm font-semibold uppercase tracking-wider">Active Workers</span>
            <Activity size={18} className="text-info" />
          </div>
          <div className="text-3xl font-bold">{loading ? '-' : workers.length}</div>
        </div>
        
        <div className="glass-panel glass-panel-hover flex flex-col gap-2">
          <div className="flex items-center justify-between text-muted">
            <span className="text-sm font-semibold uppercase tracking-wider">Total Queues</span>
            <CheckCircle size={18} className="text-success" />
          </div>
          <div className="text-3xl font-bold">{loading ? '-' : queues.length}</div>
        </div>
        
        <div className="glass-panel glass-panel-hover flex flex-col gap-2">
          <div className="flex items-center justify-between text-muted">
            <span className="text-sm font-semibold uppercase tracking-wider">Jobs Processed</span>
            <Clock size={18} className="text-primary" />
          </div>
          <div className="text-3xl font-bold text-gradient">24,592</div>
          <div className="text-xs text-success">+14% from last hour</div>
        </div>
        
        <div className="glass-panel glass-panel-hover flex flex-col gap-2">
          <div className="flex items-center justify-between text-muted">
            <span className="text-sm font-semibold uppercase tracking-wider">Error Rate</span>
            <AlertTriangle size={18} className="text-danger" />
          </div>
          <div className="text-3xl font-bold">0.12%</div>
          <div className="text-xs text-success">-0.05% from last hour</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="glass-panel">
          <h2 className="text-lg font-semibold mb-4">Worker Health</h2>
          {loading ? (
            <div className="skeleton w-full" style={{ height: '200px' }}></div>
          ) : workers.length === 0 ? (
            <div className="text-muted text-center py-8">No active workers found.</div>
          ) : (
            <div className="flex flex-col gap-4">
              {workers.slice(0, 5).map((w: any) => (
                <div key={w.id} className="flex items-center justify-between border-b border-card-border pb-2 last:border-0">
                  <div className="flex items-center gap-3">
                    <span className="status-indicator status-active"></span>
                    <span className="font-medium">{w.hostname}</span>
                  </div>
                  <span className="text-xs text-muted">Queues: {w.queues.join(', ')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        
        <div className="glass-panel">
          <h2 className="text-lg font-semibold mb-4">Throughput (Ops/sec)</h2>
          <div className="flex items-center justify-center h-48 text-muted border border-card-border border-dashed rounded-lg">
            Chart Visualization Area
          </div>
        </div>
      </div>
    </div>
  );
}
