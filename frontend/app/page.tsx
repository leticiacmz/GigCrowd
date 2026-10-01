import { redirect } from 'next/navigation';
import { locales } from './i18n';

export default function RootPage() {
  redirect(`/${locales[0]}`);
}