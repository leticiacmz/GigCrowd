'use client';

import { forwardRef } from 'react';

interface SelectOption {
  key: string;
  label: string;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  placeholder?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ options, placeholder, className = '', ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={`
          rounded-lg border border-border bg-card-bg px-3 py-2 text-sm text-foreground placeholder:text-muted-subtle
          focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent
          transition-colors
          ${className}
        `}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
);

Select.displayName = 'Select';

export default Select;