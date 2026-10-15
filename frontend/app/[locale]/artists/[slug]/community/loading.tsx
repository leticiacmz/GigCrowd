import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/** The artist community's own loading sentence, while its posts load. */
export default async function CommunityLoading() {
  const t = await getTranslations('community');

  return <LoadingState size="page" message={t('loading')} />;
}
