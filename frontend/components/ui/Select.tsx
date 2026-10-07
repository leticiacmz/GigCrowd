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

/*
  `min-h-[44px]` matches `Input`, and it is not decoration.

  A native `<select>` sized only by its padding came out at 37px tall, which is
  below the 44px touch target and - more to the point - puts it a visible step
  below the search box sitting next to it. Two controls in one row that a reader
  is expected to hit equally should not differ by 7px in height; that reads as
  "this one is secondary" when both are equally required to narrow the list.

  It is also the only picker on the events page. On a phone a native select opens
  the platform's own wheel, which is the one genre list a thumb can actually use,
  so its target is the whole interaction - there is no second chance at it.
*/

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ options, placeholder, className = '', ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={`
          min-h-[44px]
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