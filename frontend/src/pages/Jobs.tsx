import { useState } from 'react';
import { Search, Filter } from 'lucide-react';

export default function Jobs() {
  const [jobs, setJobs] = useState([]); // Dummy for now
  
  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-bold">Job Explorer</h1>
        <button className="btn btn-primary">Enqueue Job</button>
      </div>

      <div className="glass-panel mb-6">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={18} />
            <input 
              type="text" 
              placeholder="Search jobs by ID or Name..." 
              className="w-full bg-transparent border border-card-border rounded-lg py-2 pl-10 pr-4 text-text-primary focus:outline-none focus:border-primary-color transition-colors"
            />
          </div>
          <button className="btn btn-secondary">
            <Filter size={16} />
            Filters
          </button>
        </div>
      </div>

      <div className="glass-panel">
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted">
                    No jobs found matching the criteria.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
