import { useEffect, useState } from 'react';
import { getQueues } from '../api';
import { Play, Pause, Settings } from 'lucide-react';

export default function Queues() {
  const [queues, setQueues] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getQueues().then(res => {
      setQueues(res.items || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-bold">Queue Management</h1>
        <button className="btn btn-primary">Create Queue</button>
      </div>

      <div className="glass-panel">
        {loading ? (
          <div className="skeleton w-full h-32"></div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Concurrency</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {queues.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-4 text-muted">No queues found.</td>
                  </tr>
                ) : queues.map((q: any) => (
                  <tr key={q.id}>
                    <td className="font-medium">{q.name}</td>
                    <td>
                      {q.is_paused ? (
                        <span className="badge badge-warning">Paused</span>
                      ) : (
                        <span className="badge badge-success">Active</span>
                      )}
                    </td>
                    <td>{q.priority}</td>
                    <td>{q.concurrency_limit}</td>
                    <td>
                      <div className="flex gap-2">
                        <button className="btn-icon" title={q.is_paused ? "Resume" : "Pause"}>
                          {q.is_paused ? <Play size={16} /> : <Pause size={16} />}
                        </button>
                        <button className="btn-icon" title="Settings">
                          <Settings size={16} />
                        </button>
                      </div>
                    </td>
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
