import React from 'react';

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {

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

export default function Button({

  variant = 'primary',

  size = 'md',

  animated = false,

  className = '',

  children,

  ...props

}: ButtonProps) {


  const baseStyles =
    `
    font-medium
    rounded-lg
    transition-all
    duration-300
    focus:outline-none
    focus:ring-2
    focus:ring-accent
    focus:ring-offset-2
    focus:ring-offset-background
    disabled:opacity-50
    disabled:cursor-not-allowed
    `;


  const sizeStyles = {

    sm:
      `
      px-3
      py-1.5
      text-sm
      `,

    md:
      `
      px-4
      py-2
      text-base
      `,

    lg:
      `
      px-6
      py-3
      text-lg
      `,

  };


  const animatedStyles = animated
    ? `
        hover:scale-[1.02]
        hover:opacity-95
        hover:shadow-[0_0_18px_rgba(255,0,255,.25)]
      `
    : '';


  if (variant === 'outlineGradient') {

    return (

      <button

        {...props}

        className={`
          rounded-lg
          p-[1px]
          bg-gradient-to-r
          from-accent
          to-secondary
          transition-all
          duration-300
          disabled:opacity-50
          ${animatedStyles}
          ${className}
        `}

      >

        <span

          className={`
            flex
            items-center
            justify-center
            rounded-[7px]
            bg-background
            text-white
            ${sizeStyles[size]}
          `}

        >

          {children}

        </span>

      </button>

    );

  }


  const variantStyles = {

    primary:
      `
      bg-accent
      text-white
      hover:opacity-90
      `,

    secondary:
      `
      bg-secondary
      text-white
      hover:opacity-90
      `,

    outline:
      `
      border
      border-accent
      bg-transparent
      text-accent
      hover:bg-accent/10
      `,

    neon:
      `
      bg-gradient-to-r
      from-accent
      to-secondary
      text-white
      hover:opacity-90
      `,

    ghost:
      `
      text-gray-400
      hover:text-white
      hover:bg-card-hover
      `,

  };


  return (

    <button

      {...props}

      className={`
        ${baseStyles}
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${animatedStyles}
        ${className}
      `}

    >

      {children}

    </button>

  );

}