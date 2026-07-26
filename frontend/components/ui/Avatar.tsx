import React from 'react';

interface AvatarProps {
  src?: string;
  alt?: string;
  fallback?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export default function Avatar({ src, alt, fallback, size = 'md', className = '' }: AvatarProps) {
  const sizeStyles = {
    sm: 'w-8 h-8 text-sm',
    md: 'w-10 h-10 text-base',
    lg: 'w-12 h-12 text-lg',
  };
  
  if (src) {
    return (
      <img
        src={src}
        alt={alt || 'Avatar'}
        className={`${sizeStyles[size]} rounded-full object-cover ${className}`}
      />
    );
  }
  
  return (
    <div
      className={`${sizeStyles[size]} rounded-full bg-gradient-to-br from-accent to-secondary flex items-center justify-center text-white font-bold ${className}`}
    >
      {fallback || '?'}
    </div>
  );
}
