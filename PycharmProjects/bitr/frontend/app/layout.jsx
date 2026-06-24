import "./globals.css";

export const metadata = {
  title: "Рассрочка",
  description: "Система управления рассрочкой",
  icons: {
    icon: "/logo.png",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}

