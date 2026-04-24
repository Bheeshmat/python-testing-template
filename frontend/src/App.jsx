import { useState } from 'react';
import HealthCheck from './components/HealthCheck';
import LoginForm from './components/LoginForm';
import TaskList from './components/TaskList';

export default function App() {
  const [token, setToken] = useState(null);

  return (
    <div>
      <h1>Task Manager</h1>
      <HealthCheck />
      {token ? (
        <>
          <button className="logout" onClick={() => setToken(null)}>
            Logout
          </button>
          <TaskList token={token} />
        </>
      ) : (
        <LoginForm onLogin={setToken} />
      )}
    </div>
  );
}
