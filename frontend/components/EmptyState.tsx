import React from 'react';

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export default function EmptyState({ icon = '🎵', title, description, action }: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center px-4 py-16 text-center"
    >
      <div className="mb-4 text-6xl" aria-hidden="true">
        {icon}
      </div>
      <h3 className="mb-2 text-xl font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mb-6 max-w-md text-muted">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="min-h-[44px] rounded-lg bg-accent-solid px-6 py-2 font-medium text-on-accent transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
