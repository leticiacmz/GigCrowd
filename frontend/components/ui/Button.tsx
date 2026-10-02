import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:
    | 'primary'
    | 'secondary'
    | 'outline'
    | 'outlineGradient'
    | 'ghost'
    | 'neon';

  size?: 'sm' | 'md' | 'lg';

  animated?: boolean;

  children: React.ReactNode;
}

/**
 * Sizes are tuned so the smallest variant still clears a comfortable touch
 * target on mobile (sm is 36px, md 44px, lg 52px).
 */
const sizeStyles: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-3.5 py-2 text-sm min-h-[36px]',
  md: 'px-4 py-2.5 text-base min-h-[44px]',
  lg: 'px-6 py-3 text-lg min-h-[52px]',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  animated = false,
  className = '',
  children,
  ...props
}: ButtonProps) {
  const baseStyles = `
    font-medium
    rounded-lg
    inline-flex
    items-center
    justify-center
    transition-all
    duration-300
    focus:outline-none
    focus-visible:ring-2
    focus-visible:ring-accent
    focus-visible:ring-offset-2
    focus-visible:ring-offset-background
    disabled:opacity-50
    disabled:cursor-not-allowed
  `;

  const animatedStyles = animated
    ? `
        hover:scale-[1.02]
        hover:opacity-95
        hover:shadow-[0_0_18px_rgba(255,0,255,.25)]
      `
    : '';

  // The gradient outline draws the gradient on the button and an opaque
  // inner surface, so the label keeps the theme's foreground colour.
  if (variant === 'outlineGradient') {
    return (
      <button
        {...props}
        className={`
          rounded-lg
          p-[1.5px]
          bg-gradient-to-r
          from-gradient-from
          to-gradient-to
          transition-all
          duration-300
          focus:outline-none
          focus-visible:ring-2
          focus-visible:ring-accent
          focus-visible:ring-offset-2
          focus-visible:ring-offset-background
          disabled:opacity-50
          disabled:cursor-not-allowed
          ${className}
        `}
      >
        <span
          className={`
            flex
            w-full
            items-center
            justify-center
            rounded-[6px]
            bg-card-bg
            text-foreground
            ${sizeStyles[size]}
          `}
        >
          {children}
        </span>
      </button>
    );
  }

  // `outlineGradient` is handled above with its own markup.
  const variantStyles: Record<
    Exclude<NonNullable<ButtonProps['variant']>, 'outlineGradient'>,
    string
  > = {
    primary: `
      bg-accent-solid
      text-on-accent
      hover:opacity-90
    `,
    secondary: `
      bg-secondary-solid
      text-white
      hover:opacity-90
    `,
    outline: `
      border
      border-accent
      bg-transparent
      text-accent-text
      hover:bg-accent/10
    `,
    neon: `
      bg-gradient-to-r
      from-gradient-from
      to-gradient-to
      text-white
      hover:opacity-90
    `,
    ghost: `
      text-muted
      hover:text-foreground
      hover:bg-card-hover
    `,
  };

  return (
    <button
      {...props}
      className={`
        ${baseStyles}
        ${variantStyles[variant as Exclude<
          NonNullable<ButtonProps['variant']>,
          'outlineGradient'
        >]}
        ${sizeStyles[size]}
        ${animatedStyles}
        ${className}
      `}
    >
      {children}
    </button>
  );
}
