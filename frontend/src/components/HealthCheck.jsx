import { useState, useEffect } from 'react';
import { getHealth } from '../api';

export default function HealthCheck() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getHealth().then(({ data, error }) => {
      if (error) setError(error);
      else setHealth(data);
    });
  }, []);

  if (error) return <div className="health err">API: {error}</div>;
  if (!health) return <div className="health">Checking API...</div>;
  return <div className="health ok">API: {health.status} (v{health.version})</div>;
}
