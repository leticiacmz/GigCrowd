import { Inter } from 'next/font/google';
import { getMessages } from 'next-intl/server';
import { notFound } from 'next/navigation';
import Navbar from '@/components/Navbar';
import '../globals.css';

const inter = Inter({ subsets: ['latin'] });

interface LocaleLayoutProps {
  children: React.ReactNode;
  params: { locale: string };
}

export async function generateStaticParams() {
  return [{ locale: 'en' }, { locale: 'pt-BR' }, { locale: 'es' }];
}

export default async function LocaleLayout({
  children,
  params,
}: LocaleLayoutProps) {
  const locale = params.locale;

  try {
    const messages = await getMessages({ locale });
    return (
      <html lang={locale}>
        <head>
          <link rel="manifest" href="/manifest.json" />
        </head>
        <body className={inter.className}>
          <Navbar messages={messages} />
          {children}
        </body>
      </html>
    );
  } catch {
    notFound();
  }
}