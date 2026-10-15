import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/** The event page's own message, announced while its data is fetched. */
export default async function EventLoading() {
  const t = await getTranslations('event');

  return <LoadingState size="page" message={t('loading')} />;
}
