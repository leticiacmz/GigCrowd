import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/**
 * A festival page assembles identity, every date and the lineup of one date
 * in one request; this covers the trip from the series address too, so the
 * festival reads as "loading the festival" rather than as a blank screen.
 */
export default async function FestivalSeriesLoading() {
  const t = await getTranslations('festivals');

  return <LoadingState size="page" message={t('loading')} />;
}
