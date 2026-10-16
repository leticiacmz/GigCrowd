'use client';

/**
 * A festival, reached through one of its dates.
 *
 * The festival has a canonical address of its own - the series it is, at
 * `/festivals/series/{seriesId}` - and both addresses fetch the same response
 * from the same service, rendered by the shared `FestivalDetails` view. This
 * address stays because it is the festival a reader is already standing on:
 * the event page links here, so opening the festival costs no second lookup
 * of which date brought the reader.
 */
import {
  useCallback,
  useEffect,
  useState,
} from 'react';

import { useParams } from 'next/navigation';

import { eventAPI } from '../../../lib/api';

import type { Locale } from '../../../i18n';

import { resolveLocale } from '../../../lib/dates';

import FestivalDetails, {
  type Festival,
} from '../../../../components/festival/FestivalDetails';


export default function FestivalPage() {
  const params = useParams();
  const locale = resolveLocale(params.locale as string);
  const eventId = params.id as string;

  const [festival, setFestival] = useState<Festival | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const data = await eventAPI.getFestival(eventId);

      setFestival(data);
      setNotFound(false);
    } catch {
      // A 404 here is a real answer: the event is not a festival date, so there
      // is no festival page to show rather than a page waiting to load.
      setFestival(null);
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <FestivalDetails
      festival={festival}
      loading={loading}
      notFound={notFound}
      eventId={eventId}
      locale={locale}
      onReload={load}
    />
  );
}
