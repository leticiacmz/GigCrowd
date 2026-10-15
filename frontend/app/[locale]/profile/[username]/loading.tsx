import { getTranslations } from 'next-intl/server';

import LoadingState from '@/components/LoadingState';

/** A profile fetch, announced with the generic loading sentence. */
export default async function ProfileLoading() {
  const t = await getTranslations('common');

  return <LoadingState size="page" message={t('loading')} />;
}
