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
          className="mb-1 block text-sm font-medium text-gray-300"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`
          w-full
          rounded-lg
          border
          border-border
          bg-card-bg
          px-4
          py-2.5
          text-foreground
          placeholder-gray-500
          transition-all
          duration-200
          focus:border-accent
          focus:outline-none
          focus:ring-1
          focus:ring-accent
          ${error ? 'border-red-500' : ''}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-red-500">{error}</p>
      )}
    </div>
  );
}
