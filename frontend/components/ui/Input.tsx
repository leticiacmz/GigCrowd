import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export default function Input({
  label,
  error,
  className = '',
  id,
  ...props
}: InputProps) {
  const inputId = id || props.name;

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1 block text-sm font-medium text-foreground"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`
          w-full
          min-h-[44px]
          rounded-lg
          border
          border-border
          bg-card-bg
          px-4
          py-2.5
          text-foreground
          placeholder:text-muted-subtle
          transition-all
          duration-200
          focus:border-accent
          focus:outline-none
          focus:ring-1
          focus:ring-accent
          ${error ? 'border-accent' : ''}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p role="alert" className="mt-1 text-sm text-accent-text">
          {error}
        </p>
      )}
    </div>
  );
}
