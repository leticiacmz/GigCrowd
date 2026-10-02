import React from 'react';

interface AvatarProps {
  src?: string;
  alt?: string;
  fallback?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeStyles = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-12 h-12 text-base',
};

export default function Avatar({
  src,
  alt,
  fallback,
  size = 'md',
  className = '',
}: AvatarProps) {
  const sizing = `${sizeStyles[size]} shrink-0 rounded-full`;

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={alt || ''}
        loading="lazy"
        className={`${sizing} object-cover ${className}`}
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      className={[
        sizing,
        'flex items-center justify-center bg-gradient-to-br',
        'from-gradient-text-from to-gradient-text-to',
        'font-bold text-white',
        className,
      ].join(' ')}
    >
      {fallback || (alt ? alt.charAt(0).toUpperCase() : '?')}
    </div>
  );
}
