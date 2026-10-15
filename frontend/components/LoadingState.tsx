import React from 'react';

/*
  The one loading state shown wherever the app waits for data.

  Its visual is the same one the artist flow already uses - the GigCrowd
  icon with a gradient ring turning around it, drawn from the design
  tokens every filled surface uses - so "waiting" looks the same on every
  page. Three sizes cover the contexts it appears in: a whole page, a
  section inside a page, and a single row of content.

  Accessibility: the message lives in a `role="status"` / `aria-live`
  region and is announced when it changes, not re-announced on every
  render. The ring is decoration and hidden from assistive technology.
  Under `prefers-reduced-motion` the ring stops turning outright (see
  globals.css) and the message alone carries the state.

  The state is always someone else's real async work ending - this
  component never animates on a timer of its own, so when the data
  arrives, the loading leaves.
*/

interface LoadingStateProps {
  /** Localized message from the caller; `''` renders no text at all. */
  message?: string;
  /** `page` (default) for a full view, `section` inside one, `inline` in a row. */
  size?: 'page' | 'section' | 'inline';
}

const SIZES: Record<
  NonNullable<LoadingStateProps['size']>,
  { wrapper: string; orbit: string; icon: string; text: string }
> = {
  page: {
    wrapper: 'py-16',
    orbit: '',
    icon: 'h-10 w-10 rounded-lg',
    text: 'text-base',
  },
  section: {
    wrapper: 'py-8',
    orbit: 'loading-orbit--section',
    icon: 'h-6 w-6 rounded-md',
    text: 'text-sm',
  },
  inline: {
    wrapper: 'py-2',
    orbit: 'loading-orbit--inline',
    icon: 'h-4 w-4 rounded',
    text: 'text-sm',
  },
};

export default function LoadingState({
  message = 'Loading...',
  size = 'page',
}: LoadingStateProps) {
  const scale = SIZES[size];

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center px-4 ${scale.wrapper}`}
    >
      <div
        className={`loading-orbit ${scale.orbit}`.trim()}
        aria-hidden="true"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/icons/icon-192x192.png"
          alt=""
          width={40}
          height={40}
          className={scale.icon}
        />
      </div>

      {message ? (
        <p className={`mt-4 text-muted ${scale.text}`}>{message}</p>
      ) : null}
    </div>
  );
}
