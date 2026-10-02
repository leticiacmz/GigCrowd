import React from 'react';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode;
  variant?: 'default' | 'accent' | 'secondary' | 'outline';
  size?: 'sm' | 'md';
  className?: string;
}

/**
 * The shared label.
 *
 * Unrecognised props reach the root element so callers can attach
 * `data-testid` and `aria-*` without a wrapper around every badge.
 */
export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  className = '',
  ...props
}: BadgeProps) {
  const baseStyles = 'inline-flex items-center font-medium rounded-full';

  /*
   * Text colours come from the semantic tokens rather than fixed greys, so a
   * badge keeps AA contrast in both light and dark mode. Tinted backgrounds
   * are paired with the matching accent/secondary *text* token.
   */
  const variantStyles = {
    default: 'bg-card-bg text-foreground border border-border',
    accent: 'bg-accent/10 text-accent-text border border-accent/30',
    secondary: 'bg-secondary/10 text-secondary border border-secondary/30',
    outline: 'border border-border text-muted',
  };

  const sizeStyles = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
  };

  return (
    <span
      {...props}
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
    >
      {children}
    </span>
  );
}
