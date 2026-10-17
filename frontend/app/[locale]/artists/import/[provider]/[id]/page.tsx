'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';

import { artistAPI } from '@/app/lib/api';
import {
  artistPagePath,
  sharedArtistImportPool,
} from '@/app/lib/artistSync';
import ArtistSyncLoading from '@/components/ui/ArtistSyncLoading';

/*
  The address that imports one artist.

  Pressing an announced name that GigCrowd does not hold used to run the
  import on the page the name was on, which parked the reader there for as
  long as the import took - a minute or more - because the import's answer was
  a slug and nothing was addressable until it arrived. This page is that
  address: it shows the app's own loading state from its first frame, runs the
  import behind it, and the moment the import answers with a slug, replaces
  itself with the canonical artist page.

  The work is deduplicated across mounts by the shared import pool, so a React
  double mount, a repress, or a second visit while the first import is still
  running joins that import instead of starting another one. A failure is a
  state of this same page: the reader can try again - a real second attempt,
  since the failed one is forgotten - or leave, and neither is blocked by the
  import.

  The name in `?name=` is read imperatively, the same way the auth pages read
  `next`, so the page stays statically prerenderable; it is a hint for the
  message and for the identity check, never a match.
*/

/**
 * The artist name the previous page carried as a hint, if it carried one.
 *
 * Read after mount rather than during render: the server rendering this page
 * has no query string, and inventing a name for the first paint would only
 * make hydration disagree with the HTML.
 */
function readArtistName(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const value = new URLSearchParams(window.location.search).get('name');
  const trimmed = value?.trim();

  return trimmed ? trimmed : null;
}

export default function ArtistImportPage() {
  const params = useParams<{
    locale: string;
    provider: string;
    id: string;
  }>();

  const locale = params?.locale ?? 'en';
  const provider = params?.provider ?? '';
  const providerArtistId = params?.id ?? '';

  const router = useRouter();

  const [name, setName] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setName(readArtistName());
  }, []);

  useEffect(() => {
    if (!provider || !providerArtistId) {
      setFailed(true);
      return;
    }

    let cancelled = false;

    setFailed(false);

    sharedArtistImportPool
      .open(
        {
          provider,
          providerArtistId,
          name: readArtistName(),
        },
        async (request) => {
          const response = await artistAPI.importArtist(
            request.providerArtistId,
            request.provider,
            { name: request.name ?? undefined },
          );

          if (!response?.slug) {
            throw new Error('artist import answered without a slug');
          }

          return { slug: response.slug };
        },
      )
      .then((outcome) => {
        if (cancelled) {
          return;
        }

        router.replace(artistPagePath(locale, outcome.slug));
      })
      .catch(() => {
        if (cancelled) {
          return;
        }

        setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [attempt, locale, provider, providerArtistId, router]);

  function retry() {
    setFailed(false);
    setAttempt((value) => value + 1);
  }

  return (
    <div
      className="flex min-h-[60vh] items-center justify-center px-4"
      data-testid="artist-import-page"
    >
      <ArtistSyncLoading
        phase="importing"
        artistName={name}
        failure={failed ? 'failed' : null}
        onRetry={failed ? retry : undefined}
        onClose={failed ? () => router.back() : undefined}
      />
    </div>
  );
}
