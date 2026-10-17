import Link from 'next/link';
import { useTranslations } from 'next-intl';

import type { Locale } from '@/app/i18n';


/**
 * One announced performer, on a festival or an event page.
 *
 * An entry links when its identity was validated, and is a plain name when it
 * was not. There were two other states here first, and both were wrong in the
 * same way: a name carrying "not on GigCrowd yet", and a link straight out to
 * Songkick for an id taken off a festival page. One announced a gap in the
 * middle of a poster; the other dressed an unchecked id up as a confirmed one.
 *
 * So the rule is one line: a link claims an artist exists here, and that claim
 * is only made once the artist's own Songkick page has confirmed it. An entry
 * with an announced Songkick id but no page here is a control that *requests*
 * that confirmation: it links to the artist's import address, which runs the
 * on-demand import behind the app's loading state and hands over to the
 * artist's page the moment it exists. The control asserts nothing; the import
 * is the check - and the press never waits on it, because the import runs on
 * the address the press landed on, not on the page it left.
 *
 * A card is names only. There are no photographs and no avatars here: a lineup
 * used to render faces looked up from artist documents, and that lookup existed
 * only to dress this list. Nothing in this component fetches anything - no
 * image, no artist, no event. Nothing here creates an artist either; the
 * record is written on the import path, triggered by an explicit press, never
 * by a page load.
 */
export interface LineupPerformer {
  name: string;
  songkick_id?: string | null;
  /** The lineup entry's own Songkick-namespace slug. Data, never a link. */
  slug?: string | null;
  url?: string | null;
  genres?: string[];
  /** The GigCrowd page this entry resolved to, when one exists. */
  artist_slug?: string | null;
}

export function lineupHref(
  performer: LineupPerformer,
  locale: Locale,
): string | null {
  /*
    Only a validated identity links.

    An earlier version fell back to the lineup entry's own Songkick URL, on the
    reasoning that it was "somewhere real to go". That reasoning laundered the
    problem: the URL was parsed off a festival page by exactly the code path this
    work stopped trusting, so linking it asserted an identity nobody had checked -
    and it did so with a link, which reads as a stronger claim than a name.

    An unverified performer is now a name. That is the honest rendering of "we
    could not prove who this is", and it costs the reader nothing they did not
    already have.
  */

  if (!performer.artist_slug) {
    return null;
  }

  return `/${locale}/artists/${performer.artist_slug}`;
}

/**
 * The address that imports this entry's announced artist.
 *
 * The id is the one the lineup announced and the name is a hint; the import
 * validates both against the artist's own Songkick page. Built here rather
 * than in a shared module because this component's contract is that it
 * fetches nothing: an address is data, and following it is the reader's
 * decision, made on the address itself.
 */
export function lineupImportHref(
  performer: LineupPerformer,
  locale: Locale,
): string | null {
  const id = performer.songkick_id?.trim();

  if (!id) {
    return null;
  }

  return (
    `/${locale}/artists/import/songkick/${encodeURIComponent(id)}` +
    `?name=${encodeURIComponent(performer.name)}`
  );
}

export default function LineupPerformerCard({
  performer,
  locale,
  variant = 'poster',
  testId = 'festival-lineup-entry',
}: {
  performer: LineupPerformer;
  locale: Locale;
  variant?: 'poster' | 'row';
  testId?: string;
}) {
  const t = useTranslations('festivals');

  const href = lineupHref(performer, locale);

  const isRow = variant === 'row';

  /*
    An identity this system could not establish gets the name and nothing else.

    There used to be a label here saying the artist was not on GigCrowd yet,
    which was honest but useless: a reader looking at a poster wants to press
    the name. Announced performers are now validated against the artist's own
    Songkick page and created only when that page confirms the identity, so a
    name that is not linked is a name whose identity could not be *proved* -
    not a failure, and not something to announce with an error-shaped message
    in the middle of a festival lineup.

    An entry that announced a Songkick id links to the import address for that
    id: pressing it asks for that same proof under the same identity rules,
    on a page that shows the wait instead of holding the press. An entry
    without an id stays a name - there is nothing safe to identify the
    artist by.
  */
  if (!href) {
    const importHref = lineupImportHref(performer, locale);

    const text = (
      <span
        className={
          isRow
            ? 'block font-medium truncate'
            : 'break-words text-sm font-semibold leading-snug'
        }
      >
        {performer.name}
      </span>
    );

    const className = isRow
      ? 'flex items-center gap-3 rounded-xl border border-border bg-background/20 p-4'
      : 'rounded-xl border border-border bg-background/20 p-2';

    if (!importHref) {
      return (
        <div
          className={className}
          data-testid={testId}
          data-lineup-linked="false"
        >
          {text}
        </div>
      );
    }

    return (
      <Link
        href={importHref}
        className={`${className} w-full text-left transition-colors hover:border-accent hover:bg-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent`}
        data-testid={testId}
        data-lineup-linked="false"
        data-lineup-action="import"
      >
        {text}

        <span
          className="
            mt-1
            block
            text-[11px]
            leading-tight
            text-muted-subtle
          "
        >
          {t('openArtist')}
        </span>
      </Link>
    );
  }

  const body = isRow ? (
    <div
      className="
        flex
        items-center
        gap-3
        rounded-xl
        border
        border-border
        bg-background/20
        p-4
        text-left
      "
    >
      <span className="min-w-0 flex-1">
        <span className="block font-medium truncate">
          {performer.name}
        </span>

        <span
          className="
            mt-1
            flex
            items-center
            gap-1
            text-xs
            text-muted-subtle
          "
        >
          {t('openArtist')} <span aria-hidden>→</span>
        </span>
      </span>
    </div>
  ) : (
    <>
      <p
        className="
          break-words
          text-sm
          font-semibold
          leading-snug
          transition-colors
          group-hover:text-accent-text
        "
      >
        {performer.name}
      </p>

      <p
        className="
          mt-1
          text-[11px]
          leading-tight
          text-muted-subtle
        "
      >
        {t('openArtist')}
      </p>
    </>
  );

  /*
    Vertical by default. A lineup is the one place a festival page reads as a
    poster, and a poster stacks the names; the horizontal arrangement this
    replaced turned a five-across grid into five cramped rows of text.
  */
  const className = isRow
    ? 'group block transition-colors hover:border-accent hover:bg-card-hover'
    : 'group block rounded-xl border border-border bg-background/20 p-2 text-left transition-colors hover:border-accent hover:bg-card-hover';

  return (
    <Link
      href={href}
      data-testid={testId}
      data-lineup-linked="true"
      className={className}
    >
      {body}
    </Link>
  );
}
