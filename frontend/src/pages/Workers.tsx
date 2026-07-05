import { useEffect, useState } from 'react';
import { getWorkers } from '../api';
import { Activity } from 'lucide-react';

export default function Workers() {
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getWorkers().then(res => {
      setWorkers(res.items || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">Workers Monitor</h1>

      <div className="glass-panel">
        {loading ? (
          <div className="skeleton w-full h-32"></div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Hostname</th>
                  <th>Status</th>
                  <th>Assigned Queues</th>
                  <th>Last Heartbeat</th>
                </tr>
              </thead>
              <tbody>
                {workers.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="text-center py-4 text-muted">No active workers found.</td>
                  </tr>
                ) : workers.map((w: any) => (
                  <tr key={w.id}>
                    <td className="font-medium flex items-center gap-2">
                      <Activity size={16} className="text-primary" />
                      {w.hostname}
                    </td>
                    <td>
                      <span className={`badge ${w.is_active ? 'badge-success' : 'badge-danger'}`}>
                        {w.is_active ? 'Online' : 'Offline'}
                      </span>
                    </td>
                    <td>
                      <div className="flex gap-1 flex-wrap">
                        {w.queues.map((q: string) => (
                          <span key={q} className="badge badge-neutral bg-transparent border border-card-border">{q}</span>
                        ))}
                      </div>
                    </td>
                    <td className="text-sm text-muted">{new Date(w.last_heartbeat).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
