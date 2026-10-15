import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/**
 * A festival page assembles identity, every date and the lineup of the date
 * asked about in one request; this covers the trip, so a big series reads as
 * "loading the festival" rather than as a blank screen.
 */
export default async function FestivalLoading() {
  const t = await getTranslations('festivals');

  return <LoadingState size="page" message={t('loading')} />;
}
