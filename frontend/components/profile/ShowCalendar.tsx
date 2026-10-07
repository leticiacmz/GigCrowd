'use client';

/**
 * The shows somebody actually went to, as a month you choose.
 *
 * A concert history is a diary, and a diary is read by remembering when things
 * happened. A month grid does that in a way a list of rows cannot: it shows the
 * gaps, so a heavy month looks heavy and a quiet summer looks quiet.
 *
 * Only days with an attended show are marked. A show somebody meant to go to, or
 * an act that was on a festival bill, does not put them in a room - so neither
 * marks a day here. That distinction is the whole reason this is not built from
 * the same rows as the Want to Go and Maybe lists.
 *
 * Closed by default, and that is the important change. It used to sit open in
 * the profile, permanently taking up a month-shaped hole above a list of shows
 * that nobody had scrolled to yet. A diary is read when the reader decides to
 * read it, so the calendar is now a button until they do.
 *
 * It is a popover on a pointer device and a sheet on a small one. A popover
 * anchored to the button works with a mouse and is wrong on a phone, where it
 * would cover the list and have nowhere sensible to dismiss to; a sheet from
 * the bottom edge is the shape a phone already expects. Both render the same
 * grid, so there is only one calendar to reason about.
 *
 * The month is fetched on its own rather than derived from the loaded shows, so
 * navigating back through years costs one small query per month instead of the
 * entire history. And the year selector lists the years this profile actually
 * has shows in, because walking backwards from this year to 2021 one arrow at a
 * time is not navigation, it is a chore.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';

import { useLocale, useTranslations } from 'next-intl';

import { userAPI } from '@/app/lib/api';

const WEEKDAY_KEYS = [
  'calendar.weekdays.mon',
  'calendar.weekdays.tue',
  'calendar.weekdays.wed',
  'calendar.weekdays.thu',
  'calendar.weekdays.fri',
  'calendar.weekdays.sat',
  'calendar.weekdays.sun',
] as const;

/** Monday-first: the grid leads with Monday and this orders the headings. */
const WEEKDAY_ORDER = [0, 1, 2, 3, 4, 5, 6];

interface CalendarProps {
  username: string;

  /**
   * Which day the reader is currently looking at, so the calendar and the list can
   * agree. Set by clicking a marked day; `null` when nothing is focused.
   */
  focusDay: string | null;

  /** Called when a marked day is chosen, or cleared by choosing it again. */
  onFocusDay: (day: string | null) => void;

  /**
   * Months that already carry a day, so the year selector can offer the years
   * this profile has shows in. Fetched once by the parent and shared with the
   * month summary, which would otherwise need a request per month just to
   * decide whether to draw a dot next to it.
   */
  yearsWithShows?: { year: number; shows: number }[];
}

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

function monthKey(year: number, month: number): string {
  return `${year}-${pad(month)}`;
}

/** The days of a month laid out in whole weeks, Monday first. */
function buildGrid(year: number, month: number): (string | null)[] {
  const first = new Date(Date.UTC(year, month - 1, 1));

  // `getUTCDay` is 0 for Sunday; the grid leads with Monday.
  const leading = (first.getUTCDay() + 6) % 7;

  const daysInMonth = new Date(
    Date.UTC(year, month, 0)
  ).getUTCDate();

  const cells: (string | null)[] = Array.from(
    { length: leading },
    () => null
  );

  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(monthKey(year, month) + '-' + pad(day));
  }

  while (cells.length % 7 !== 0) {
    cells.push(null);
  }

  return cells;
}

function shiftMonth(
  year: number,
  month: number,
  by: number
): { year: number; month: number } {
  // Months are carried as a zero-based index so December rolls into January
  // without a special case, which is where this kind of arithmetic usually goes
  // wrong.
  const index = year * 12 + (month - 1) + by;

  return {
    year: Math.floor(index / 12),
    // `%` on a negative index is negative in JavaScript, so a step backwards
    // from January would otherwise produce month 0.
    month: ((index % 12) + 12) % 12 + 1,
  };
}

/** The twelve month names in this locale, for the month selector. */
function monthNames(locale: string): string[] {
  const formatter = new Intl.DateTimeFormat(locale, {
    month: 'long',
    timeZone: 'UTC',
  });

  return Array.from({ length: 12 }, (_, index) =>
    formatter.format(new Date(Date.UTC(2021, index, 1)))
  );
}

/**
 * Whether the viewport is wide enough for a floating panel.
 *
 * Decided in JavaScript rather than with two copies of the panel behind
 * responsive classes, because two copies means two sets of month and year
 * selects in the document at once: one invisible, unreachable by pointer, and
 * perfectly reachable by keyboard. Whichever copy is not on screen would still
 * be a control, and a screen reader would offer the reader a duplicate.
 *
 * There is one panel. Only its geometry changes.
 */
function useIsSheet(): boolean {
  const [isSheet, setIsSheet] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return;
    }

    const query = window.matchMedia('(max-width: 639px)');

    const sync = () => setIsSheet(query.matches);

    sync();

    query.addEventListener('change', sync);

    return () => query.removeEventListener('change', sync);
  }, []);

  return isSheet;
}

export default function ShowCalendar({
  username,
  focusDay,
  onFocusDay,
  yearsWithShows,
}: CalendarProps) {
  const t = useTranslations('profile');
  const locale = useLocale();

  const today = new Date();

  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [days, setDays] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const headingId = useId();

  const isSheet = useIsSheet();

  const months = useMemo(
    () => monthNames(locale),
    [locale]
  );

  // The years worth offering. The ones this profile has shows in, always
  // including the current year - a reader opening the calendar in a year with
  // nothing logged yet should still be able to say so explicitly rather than
  // find the option missing.
  const yearOptions = useMemo(() => {
    const known = new Set(
      (yearsWithShows || []).map((row) => row.year)
    );

    known.add(today.getFullYear());

    return Array.from(known).sort((a, b) => b - a);
  }, [yearsWithShows]);

  // One request per month, and only once the calendar is actually open. There
  // is nothing to fetch for a reader who never opens it.
  const load = useCallback(async () => {
    setLoading(true);

    try {
      const data = await userAPI.getProfileShowCalendar(
        username,
        year,
        month
      );

      setDays(data.days ?? {});
    } catch {
      // A month that could not be read is shown as empty rather than leaving a
      // spinner where the reader expects a month.
      setDays({});
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }, [month, username, year]);

  useEffect(() => {
    if (!open) {
      return;
    }

    load();
  }, [load, open]);

  const close = useCallback(() => {
    setOpen(false);

    // Focus goes back where it came from, so dismissing with the keyboard does
    // not strand the reader at the top of the document.
    triggerRef.current?.focus();
  }, []);

  // Dismiss on Escape, and on a click outside. Both are what a popover is
  // expected to do, and both are what a screen-reader user needs to leave one.
  useEffect(() => {
    if (!open) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();

        close();
      }
    }

    function onPointerDown(event: MouseEvent) {
      const container = containerRef.current;

      if (container && !container.contains(event.target as Node)) {
        close();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [close, open]);

  const grid = buildGrid(year, month);
  const marked = Object.keys(days);
  const total = Object.values(days).reduce(
    (sum, count) => sum + count,
    0
  );

  function move(by: number) {
    const next = shiftMonth(year, month, by);

    setYear(next.year);
    setMonth(next.month);
  }

  const summary = t('calendar.summary', {
    shows: total,
    days: marked.length,
  });

  // The trigger says which month it will open on, so it is a label for what is
  // about to appear rather than a mystery icon.
  const triggerLabel = new Intl.DateTimeFormat(locale, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, 1)));

  const body = (
    <>
      <div className="mb-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => move(-1)}
          className="flex h-11 w-11 items-center justify-center rounded-full text-lg text-muted-subtle transition hover:bg-surface-raised hover:text-foreground focus-ring"
          data-testid="calendar-previous"
          aria-label={t('calendar.previous')}
        >
          <span aria-hidden="true">‹</span>
        </button>

        <p
          className="text-center text-sm font-medium text-foreground"
          data-testid="calendar-month-label"
          id={headingId}
        >
          {triggerLabel}
        </p>

        <button
          type="button"
          onClick={() => move(1)}
          className="flex h-11 w-11 items-center justify-center rounded-full text-lg text-muted-subtle transition hover:bg-surface-raised hover:text-foreground focus-ring"
          data-testid="calendar-next"
          aria-label={t('calendar.next')}
        >
          <span aria-hidden="true">›</span>
        </button>
      </div>

      {/*
        Year first, then month. That order is the one that saves the reader
        time, because a year is the coarser choice: somebody who wants March
        2021 picks 2021 and then March, while somebody who wants "this
        December" can skip the year entirely since it is already correct.

        The selectors are the accessible controls for the arrows above. The
        arrows stay because stepping through months is a browsing gesture and a
        dropdown is a targeting one, and a diary needs both.
      */}
      <div className="mb-3 flex items-center gap-2">
        <label className="sr-only" htmlFor="calendar-year-select">
          {t('calendar.selectYear')}
        </label>

        <select
          id="calendar-year-select"
          value={String(year)}
          onChange={(event) => setYear(Number(event.target.value))}
          data-testid="calendar-year-select"
          className="
            min-h-[44px]
            flex-1
            rounded-lg
            border
            border-border
            bg-background
            px-3
            py-2
            text-sm
            text-foreground
            outline-none
            focus:border-accent
          "
        >
          {/*
            A year the reader navigated to with the arrows but that has no shows
            is still selectable, so a month they reached cannot silently vanish
            from the list they are choosing out of.
          */}
          {!yearOptions.includes(year) && (
            <option value={String(year)}>{year}</option>
          )}

          {yearOptions.map((option) => (
            <option key={option} value={String(option)}>
              {option}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="calendar-month-select">
          {t('calendar.selectMonth')}
        </label>

        <select
          id="calendar-month-select"
          value={String(month)}
          onChange={(event) => setMonth(Number(event.target.value))}
          data-testid="calendar-month-select"
          className="
            min-h-[44px]
            flex-1
            rounded-lg
            border
            border-border
            bg-background
            px-3
            py-2
            text-sm
            text-foreground
            outline-none
            focus:border-accent
          "
        >
          {months.map((name, index) => (
            <option key={name} value={String(index + 1)}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div
        className="mb-1 grid grid-cols-7 gap-1 text-center text-[11px] uppercase tracking-wide text-muted-subtle"
        aria-hidden="true"
      >
        {WEEKDAY_ORDER.map((source, index) => (
          <span key={source}>
            {t(WEEKDAY_KEYS[index])}
          </span>
        ))}
      </div>

      <div
        className="grid grid-cols-7 gap-1"
        data-testid="calendar-grid"
        aria-busy={loading}
      >
        {grid.map((iso, index) => {
          if (!iso) {
            return (
              <span
                key={`empty-${index}`}
                className="h-9"
                aria-hidden="true"
              />
            );
          }

          const count = days[iso] ?? 0;
          const isMarked = count > 0;
          const isFocused = focusDay === iso;

          const day = Number(iso.slice(-2));

          if (!isMarked) {
            return (
              <span
                key={iso}
                className="flex h-9 items-center justify-center rounded-lg text-xs text-muted-subtle/60"
                data-testid="calendar-day"
                data-day={iso}
                data-marked="false"
              >
                {day}
              </span>
            );
          }

          return (
            <button
              key={iso}
              type="button"
              onClick={() => onFocusDay(isFocused ? null : iso)}
              className={[
                'relative flex h-9 items-center justify-center rounded-lg text-xs font-medium transition focus-ring',
                isFocused
                  ? 'bg-accent text-accent-foreground'
                  : 'bg-accent/15 text-accent hover:bg-accent/25',
              ].join(' ')}
              data-testid="calendar-day"
              data-day={iso}
              data-marked="true"
              data-count={count}
              aria-pressed={isFocused}
              aria-label={t('calendar.dayWithShows', {
                day,
                shows: count,
              })}
            >
              {day}

              {count > 1 && (
                <span
                  className="absolute bottom-0.5 right-1 text-[9px] leading-none text-accent/80"
                  data-testid="calendar-day-count"
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/*
        A month with nothing in it is stated rather than left blank, because an
        empty grid and an empty history look identical otherwise and mean very
        different things.
      */}
      {!loading && loaded && total === 0 && (
        <p
          className="mt-3 text-center text-xs text-muted-subtle"
          data-testid="calendar-empty"
        >
          {t('calendar.emptyMonth')}
        </p>
      )}

      {focusDay && (
        <p
          className="mt-3 text-center text-xs text-muted-subtle"
          data-testid="calendar-focus-note"
        >
          {t('calendar.filtering', { day: focusDay })}
        </p>
      )}

      <p
        className="mt-3 text-center text-xs text-muted-subtle"
        data-testid="calendar-summary"
      >
        {summary}
      </p>
    </>
  );

  return (
    <div
      className="relative"
      ref={containerRef}
      data-testid="profile-show-calendar"
      data-calendar-month={monthKey(year, month)}
      data-calendar-open={open ? 'true' : 'false'}
    >
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={headingId}
        aria-label={t('calendar.open')}
        data-testid="calendar-trigger"
        className="
          inline-flex
          min-h-[44px]
          items-center
          gap-2
          rounded-full
          border
          border-hairline-strong
          bg-surface-raised/40
          px-4
          py-2
          text-sm
          text-foreground
          transition
          hover:border-accent
          focus-ring
        "
      >
        <span aria-hidden="true">🗓</span>

        <span>{triggerLabel}</span>

        <span
          className="text-xs text-muted-subtle"
          data-testid="calendar-trigger-summary"
        >
          {summary}
        </span>

        <span
          aria-hidden="true"
          className="text-xs text-muted-subtle"
        >
          {open ? '▲' : '▼'}
        </span>
      </button>

      {/*
        One panel, placed twice over - once anchored for a pointer, once as a
        sheet from the bottom edge for a thumb - and only one of the two is ever
        in the DOM. `isSheet` is the whole of the difference: geometry, not
        behaviour. Rendering both and hiding one with a class would leave a
        second set of month and year selects that nobody can see and a keyboard
        can still tab to.
      */}
      {open && !isSheet && (
        <div
          className="
            absolute
            left-0
            top-full
            z-30
            mt-2
            w-[22rem]
            rounded-2xl
            border
            border-hairline-strong
            bg-card-bg
            p-4
            shadow-lg
          "
          data-testid="calendar-popover"
          role="dialog"
          aria-label={t('calendar.heading')}
        >
          {body}
        </div>
      )}

      {open && isSheet && (
        <div
          className="fixed inset-0 z-40 flex items-end"
          data-testid="calendar-sheet"
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={close}
            aria-hidden="true"
          />

          <div
            className="
              relative
              z-10
              w-full
              rounded-t-3xl
              border-t
              border-hairline-strong
              bg-card-bg
              pb-6
            "
            role="dialog"
            aria-label={t('calendar.heading')}
          >
            <div
              className="mx-auto mt-2 h-1 w-10 rounded-full bg-hairline-strong"
              aria-hidden="true"
            />

            <div className="flex items-center justify-between px-4 pt-2">
              <h2 className="text-sm font-semibold text-foreground">
                {t('calendar.heading')}
              </h2>

              <button
                type="button"
                onClick={close}
                className="min-h-[44px] px-3 text-sm text-accent focus-ring"
                data-testid="calendar-close"
              >
                {t('calendar.close')}
              </button>
            </div>

            <div className="pt-1 px-4">{body}</div>
          </div>
        </div>
      )}
    </div>
  );
}
