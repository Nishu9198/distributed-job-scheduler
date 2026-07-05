import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface Queue {
  id: string;
  name: string;
  is_paused: boolean;
  priority: number;
  concurrency_limit: number;
}

export interface Worker {
  id: string;
  hostname: string;
  queues: string[];
  last_heartbeat: string;
  is_active: boolean;
  status: string;
}

export interface Job {
  id: string;
  name: string;
  type: string;
  status: string;
  created_at: string;
  scheduled_at?: string;
  retry_count: number;
  max_retries: number;
}

export const getQueues = async () => {
  const res = await api.get('/queues/');
  return res.data;
};

export const getWorkers = async () => {
  const res = await api.get('/workers/');
  return res.data;
};

export const getJobs = async (queueId: string) => {
  const res = await api.get(`/queues/${queueId}/jobs`);
  return res.data;
};

export default api;
