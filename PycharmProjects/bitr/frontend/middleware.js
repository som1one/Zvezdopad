import { NextResponse } from "next/server";

export function middleware(req) {
  const url = req.nextUrl.pathname;
  
  // Пропускаем статические файлы и API роуты
  if (
    url.startsWith("/api") ||
    url.startsWith("/_next") ||
    url.startsWith("/favicon.ico") ||
    url.startsWith("/auth")
  ) {
    return NextResponse.next();
  }

  // Проверяем наличие токена в localStorage (через cookie не получится в middleware)
  // Вместо этого проверяем на клиенте, а здесь просто разрешаем доступ
  // Реальная проверка будет на клиенте через apiClient
  
  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};

