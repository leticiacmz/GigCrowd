import React from 'react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  hoverable?: boolean;
  /**
   * Opt-in button semantics.
   *
   * A card that only *adds* behaviour to clicks it already contains (links,
   * buttons) should stay a plain group, because wrapping real controls in a
   * `role="button"` element hides them from assistive technology. Pass
   * `role="button"` plus `tabIndex={0}` when the card is the only control.
   */
  role?: string;
  tabIndex?: number;
  onKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
}

/**
 * The shared surface used for every panel in the app.
 *
 * Unrecognised props are forwarded to the root element so callers can attach
 * `data-testid`, `aria-*` and event handlers without a wrapper.
 */
export default function Card({
  children,
  className = '',
  hoverable = false,
  onClick,
  onKeyDown,
  role,
  tabIndex,
  ...props
}: CardProps) {
  const baseStyles = 'bg-card-bg border border-border rounded-xl p-4';
  const hoverStyles = hoverable
    ? 'hover:border-accent hover:bg-card-hover cursor-pointer transition-all duration-200'
    : '';

  // Enter and Space activate a card that opted into button semantics.
  //
  // The handler is only attached in that case: `Card` is also rendered by
  // Server Components, which must not put a function on a host element.
  const activatable = role === 'button' && Boolean(onClick);

  const handleKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (event) => {
    onKeyDown?.(event);

    if (event.defaultPrevented || !activatable) {
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      // Dispatch a real click so the handler receives a proper MouseEvent and
      // any other click listener on the card runs exactly once.
      event.currentTarget.click();
    }
  };

  return (
    <div
      {...props}
      className={`${baseStyles} ${hoverStyles} ${className}`}
      onClick={onClick}
      onKeyDown={activatable ? handleKeyDown : onKeyDown}
      role={role}
      tabIndex={tabIndex}
    >
      {children}
    </div>
  );
}