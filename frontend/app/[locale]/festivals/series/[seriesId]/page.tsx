'use client';

/**
 * A festival, addressed by the series it is.
 *
 * This is the canonical address of a festival: the id names the series, not
 * any one of its dates, so the page outlives the editions around it - which
 * is what makes it safe to share. The `?edition=` parameter says which date's
 * lineup to open on; without it the chronologically last date is shown.
 *
 * A 24-character hexadecimal id is an event id, not a series id - the one
 * value shape the two festival routes could collide on - so it is sent to the
 * date-keyed route rather than read as a series that cannot exist.
 *
 * The edition parameter is read from the address at fetch time rather than
 * through `useSearchParams`, which would demand a Suspense boundary around
 * the whole page for a parameter only the fetch asks about.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  useParams,
  useRouter,
} from 'next/navigation';

import { eventAPI } from '../../../../lib/api';

import type { Locale } from '../../../../i18n';

import { resolveLocale } from '../../../../lib/dates';

import {
  festivalEditionFromSearch,
  resolveFestivalSeriesParam,
} from '../../../../lib/festivalSeries';

import FestivalDetails, {
  type Festival,
} from '../../../../../components/festival/FestivalDetails';


export default function FestivalSeriesPage() {
  const params = useParams();
  const router = useRouter();
  const locale = resolveLocale(params.locale as string);

  /*
    Resolved once per parameter value, not per render: a fresh object every
    render would change the fetch callback's identity on every pass, and the
    effect that calls it would refetch forever - a page permanently loading
    its festival.
  */
  const seriesParam = params.seriesId as string;
  const route = useMemo(
    () => resolveFestivalSeriesParam(seriesParam),
    [seriesParam]
  );

  const [festival, setFestival] = useState<Festival | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  // An event id handed to the series route names a date-keyed address: send
  // it there, where it resolves, rather than reading it as a series that
  // cannot exist.
  useEffect(() => {
    if (route.kind === 'legacy-event') {
      router.replace(`/${locale}/festivals/${route.eventId}`);
    }
  }, [route, locale, router]);

  const load = useCallback(async () => {
    if (route.kind !== 'series') {
      return;
    }

    setLoading(true);

    try {
      const data = await eventAPI.getFestivalSeries(
        route.seriesId,
        festivalEditionFromSearch(window.location.search)
      );

      setFestival(data);
      setNotFound(false);
    } catch {
      // A 404 here is a real answer: no stored record states this series, so
      // there is no festival page to show rather than one waiting to load.
      setFestival(null);
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [route]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <FestivalDetails
      festival={festival}
      loading={route.kind === 'legacy-event' || (route.kind === 'series' && loading)}
      notFound={route.kind === 'invalid' || notFound}
      eventId={null}
      locale={locale}
      onReload={load}
    />
  );
}
