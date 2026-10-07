import Link from 'next/link';
import { useTranslations } from 'next-intl';

import type { Locale } from '@/app/i18n';


/**
 * One announced performer, on a festival or an event page.
 *
 * An entry links when its identity was validated, and is a plain name when it was
 * not. There were two other states here first, and both were wrong in the same
 * way: a name carrying "not on GigCrowd yet", and a link straight out to
 * Songkick for an id taken off a festival page. One announced a gap in the
 * middle of a poster; the other dressed an unchecked id up as a confirmed one.
 *
 * So the rule is one line: a link claims an artist exists here, and that claim
 * is only made once the artist's own Songkick page has confirmed it. Everything
 * else renders as the name it is.
 *
 * Nothing here creates an artist. The record is written on the import path, by
 * `LineupArtistImporter`, never by a page load.
 */
export interface LineupPerformer {
  name: string;
  songkick_id?: string | null;
  slug?: string | null;
  url?: string | null;
  image?: string | null;
  genres?: string[];
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

    So the text is plain, and the absence of a link carries no accusation.
  */
  if (!href) {
    return (
      <div
        className={
          isRow
            ? 'flex items-center gap-3 rounded-xl border border-border bg-background/20 p-4'
            : 'rounded-xl border border-border bg-background/20 p-2'
        }
        data-testid={testId}
        data-lineup-linked="false"
      >
        <span
          className={
            isRow
              ? 'block font-medium truncate'
              : 'break-words text-sm font-semibold leading-snug'
          }
        >
          {performer.name}
        </span>
      </div>
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
      {performer.image ? (
        <img
          src={performer.image}
          alt=""
          loading="lazy"
          className="
            h-12
            w-12
            rounded-full
            object-cover
            shrink-0
          "
        />
      ) : (
        <div
          className="
            flex
            h-12
            w-12
            items-center
            justify-center
            rounded-full
            bg-card-hover
            text-lg
            shrink-0
          "
        >
          ♪
        </div>
      )}

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
      {performer.image ? (
        <img
          src={performer.image}
          alt=""
          loading="lazy"
          className="
            mb-2
            aspect-square
            w-full
            rounded-lg
            object-cover
            shrink-0
          "
        />
      ) : (
        <div
          className="
            mb-2
            flex
            aspect-square
            w-full
            items-center
            justify-center
            rounded-lg
            bg-card-hover
            text-3xl
            shrink-0
          "
        >
          ♪
        </div>
      )}

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
