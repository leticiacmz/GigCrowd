import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
  onClick?: () => void;
}

export default function Card({ children, className = '', hoverable = false, onClick }: CardProps) {
  const baseStyles = 'bg-card-bg border border-border rounded-xl p-4';
  const hoverStyles = hoverable ? 'hover:border-accent hover:bg-card-hover cursor-pointer transition-all duration-200' : '';
  
  return (
    <div
      className={`${baseStyles} ${hoverStyles} ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  );
}
