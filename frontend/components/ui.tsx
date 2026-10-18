import type { ReactNode } from 'react';
import { categories, type Category } from '@/lib/mock-data';

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export function CategoryBadge({ category }: { category: Category }) {
  const item = categories.find(c => c.id === category);
  if (!item) return null;
  return (
    <span
      className="category-badge"
      style={{
        color: item.color,
        backgroundColor: `${item.color}1E`,
        borderColor: `${item.color}44`,
      }}
    >
      <i style={{ background: item.color }} />
      {item.name}
    </span>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <span className="logo-symbol" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      offload<span className="logo-period">.</span>
    </span>
  );
}
