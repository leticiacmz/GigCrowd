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