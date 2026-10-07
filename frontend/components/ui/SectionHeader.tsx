import type { ReactNode } from 'react';

/**
 * The heading a section of a page opens with.
 *
 * A profile is a set of separate things someone saw, said and follows, and a
 * reader needs to be able to tell where one ends and the next begins without
 * reading every row. So each section gets the same treatment: a small accent
 * rule, a title, and an optional figure on the right.
 *
 * It is deliberately not a card. Wrapping every section in its own bordered
 * box would flatten the page into a stack of slabs; the heading and the space
 * around it do the separating.
 */
export default function SectionHeader({
  title,
  subtitle,
  count,
  action,
  id,
}: {
  title: string;
  /**
   * A line under the title saying what the section is.
   *
   * A profile is a set of separate things, and a bare heading leaves the reader
   * guessing: "Artists" could mean the artists someone follows or the ones they
   * has paid to watch. One short sentence removes the ambiguity without adding
   * another control to the page.
   */
  subtitle?: string;
  /** A figure that belongs beside the title, such as a list's real total. */
  count?: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div className="min-w-0">
        <span
          aria-hidden="true"
          className="mb-2 block h-[3px] w-8 rounded-full bg-accent"
        />

        <h2
          id={id}
          className="text-lg font-bold leading-tight text-foreground sm:text-xl"
        >
          {title}
        </h2>

        {subtitle && (
          <p
            className="mt-1 text-sm leading-snug text-muted-subtle"
            data-testid="section-subtitle"
          >
            {subtitle}
          </p>
        )}
      </div>

      {(count || action) && (
        <div className="flex shrink-0 items-center gap-2 pb-0.5">
          {count}
          {action}
        </div>
      )}
    </div>
  );
}
