import { useState, useEffect } from 'react';
import { getTasks, createTask } from '../api';

export default function TaskList({ token }) {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState('');
  const [error, setError] = useState(null);

  const fetchTasks = async () => {
    try {
      const data = await getTasks(token);
      setTasks(data);
    } catch {
      setError('Failed to load tasks');
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await createTask(token, title);
      setTitle('');
      fetchTasks();
    } catch {
      setError('Failed to create task');
    }
  };

  return (
    <div>
      <h2>Your Tasks</h2>
      <form onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="New task title..."
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button type="submit">Add Task</button>
      </form>
      {error && <p className="error">{error}</p>}
      {tasks.length === 0 ? (
        <p style={{ color: '#6b7280', marginTop: '10px' }}>No tasks yet. Create one above.</p>
      ) : (
        tasks.map((task) => (
          <div key={task.id} className="task">
            <strong>{task.title}</strong>
            <span className="task-status"> — {task.status} · {task.priority}</span>
          </div>
        ))
      )}
    </div>
  );
}
