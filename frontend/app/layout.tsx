import { Inter } from 'next/font/google'
import Navbar from '../components/Navbar'
import './globals.css'
const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: 'GigCrowd',
  description: 'A social platform for live music experiences',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Navbar />
        {children}
      </body>
    </html>
  )
}
