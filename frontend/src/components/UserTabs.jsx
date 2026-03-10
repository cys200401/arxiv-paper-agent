const USERS = [
  { id: 'user_1', label: 'Alice · cs.AI' },
  { id: 'user_2', label: 'Bob · cs.LG' },
  { id: 'user_3', label: 'Charlie · RL' },
  { id: 'smoke_test', label: 'Smoke Test' },
];

export default function UserTabs({ active, onChange }) {
  return (
    <nav className="user-tabs">
      {USERS.map(u => (
        <button
          key={u.id}
          className={`user-tab${active === u.id ? ' active' : ''}`}
          onClick={() => onChange(u.id)}
        >
          {u.label}
        </button>
      ))}
    </nav>
  );
}
