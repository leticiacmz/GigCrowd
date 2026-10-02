/**
 * Date and number formatting that follows the reader's language.
 *
 * The month and weekday names have to come from the active locale, otherwise
 * a Brazilian reader is shown English names on a page whose labels are
 * translated. Every page formats through here so one locale drives both the
 * wording and the dates.
 */
import { locales, defaultLocale, type Locale } from '@/app/i18n';

function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}

/** Narrow an arbitrary route segment to a supported locale. */
export function resolveLocale(value: string | undefined): Locale {
  return value && isLocale(value) ? value : defaultLocale;
}

/** The BCP 47 tag for a locale, for `Intl` and `localeCompare`. */
export function intlTag(locale: Locale): string {
  return locale;
}

export function formatEventDateRange(
  value: string,
  locale: Locale,
): string {
  return new Intl.DateTimeFormat(intlTag(locale), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(value));
}

export function formatEventMonthDay(
  value: string,
  locale: Locale,
): string {
  return new Intl.DateTimeFormat(intlTag(locale), {
    day: 'numeric',
    month: 'short',
  }).format(new Date(value));
}

export function formatEventTime(
  value: string,
  locale: Locale,
): string {
  return new Intl.DateTimeFormat(intlTag(locale), {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

/**
 * A date span, collapsed to one end date when both ends share a month.
 */
export function formatDateSpan(
  start: string,
  end: string | null | undefined,
  locale: Locale,
): string {
  const startDate = new Date(start);

  if (!end) {
    return formatEventDateRange(start, locale);
  }

  const endDate = new Date(end);

  const sameMonth =
    startDate.getFullYear() === endDate.getFullYear() &&
    startDate.getMonth() === endDate.getMonth();

  if (sameMonth) {
    const monthYear = new Intl.DateTimeFormat(intlTag(locale), {
      month: 'long',
      year: 'numeric',
    }).format(startDate);

    return `${formatEventMonthDay(start, locale)} – ${monthYear}`;
  }

  const from = formatEventMonthDay(start, locale);
  const to = formatEventMonthDay(end, locale);

  if (startDate.getFullYear() === endDate.getFullYear()) {
    const year = startDate.getFullYear();

    return `${from} – ${to}, ${year}`;
  }

  return `${from}, ${startDate.getFullYear()} – ${to}, ${endDate.getFullYear()}`;
}

/** Sort a list of named entries using the reader's collation. */
export function byNameInLocale<T extends { name: string }>(
  entries: T[],
  locale: Locale,
): T[] {
  return [...entries].sort((a, b) =>
    a.name.localeCompare(b.name, intlTag(locale)),
  );
}

/**
 * The fields an event's schedule is made of.
 *
 * Both dates are optional because imported events genuinely arrive without
 * them, and `is_past` is optional because it is the server's answer to the same
 * question.
 */
export interface EventSchedule {
  starts_at?: string | null;
  ends_at?: string | null;
  is_past?: boolean | null;
}

/** Parse a stored date, or `null` when it is absent or unusable. */
function parseDate(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value).getTime();

  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * The instant that decides whether an event has happened.
 *
 * The LATER of the two dates wins: a festival that is still running on its last
 * day has not happened yet, while a concert describes a single evening through
 * both dates. This mirrors `app/domain/event_schedule.py` on the backend.
 */
function referenceTime(event: EventSchedule | null | undefined): number | null {
  const startsAt = parseDate(event?.starts_at);
  const endsAt = parseDate(event?.ends_at);
  const dates = [startsAt, endsAt].filter(
    (moment): moment is number => moment !== null,
  );

  if (dates.length === 0) {
    return null;
  }

  return Math.max(...dates);
}

/**
 * Whether an event has already happened.
 *
 * The backend resolves this once in `app/domain/event_schedule.py` and ships it
 * as `is_past`, so that answer is always preferred; the local rule only runs for
 * payloads that arrive without the flag. An event with no usable date is never
 * past, because there is no evidence that it happened and guessing would offer
 * "I went" for a show that is still being announced.
 */
export function isPastEvent(
  event: EventSchedule | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!event) {
    return false;
  }

  if (typeof event.is_past === 'boolean') {
    return event.is_past;
  }

  const reference = referenceTime(event);

  return reference !== null && reference < now;
}

/**
 * Whether an event is running right now.
 *
 * This one needs an explicit end: only a provider that said when the show
 * finishes can say it is still going. An event that started earlier and carries
 * no end date is simply past, so the status never claims "happening now" for a
 * concert whose end nobody knows.
 */
export function isHappeningNow(
  event: EventSchedule | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!event || isPastEvent(event, now)) {
    return false;
  }

  const endsAt = parseDate(event.ends_at);

  if (endsAt === null) {
    return false;
  }

  const startsAt = parseDate(event.starts_at);

  return startsAt === null || startsAt <= now;
}

/**
 * The date to print for an event, or `null` when it has none.
 *
 * A festival is placed by the day it starts and a concert by the same instant,
 * so this is the first usable date rather than the one that decides whether the
 * event is over.
 */
export function eventDate(
  event: EventSchedule | null | undefined,
): string | null {
  const startsAt = event?.starts_at;

  if (startsAt && Number.isFinite(new Date(startsAt).getTime())) {
    return startsAt;
  }

  const endsAt = event?.ends_at;

  if (endsAt && Number.isFinite(new Date(endsAt).getTime())) {
    return endsAt;
  }

  return null;
}

/**
 * Format an event's date in the reader's language, or report it as unknown.
 *
 * Imported events carry no date often enough that every caller needs one place
 * to ask for the wording, rather than each screen inventing its own.
 */
export function formatEventSchedule(
  event: EventSchedule | null | undefined,
  locale: Locale,
  unknownLabel: string,
): string {
  const date = eventDate(event);

  return date ? formatEventDateRange(date, locale) : unknownLabel;
}