// middleware.ts
import { NextResponse, NextRequest } from "next/server";

async function checkAuth(req: NextRequest): Promise<boolean> {
  const api = process.env.AUTH_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE;
  if (!api) return false;
  try {
    const r = await fetch(`${api}/api/v1/auth/me`, {
      headers: { cookie: req.headers.get("cookie") ?? "" },
      cache: "no-store",
    });
    return r.ok;
  } catch {
    return false;
  }
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // 1) /login: если уже авторизован — отправляем на next/домой
  if (pathname === "/login") {
    if (await checkAuth(req)) {
      const next = req.nextUrl.searchParams.get("next");
      const safe = next && next.startsWith("/") ? next : "/";
      return NextResponse.redirect(new URL(safe, req.url));
    }
    return NextResponse.next();
  }

  // 2) защищённые пути → требуем авторизацию
  const protectedPaths = [
    pathname.startsWith("/audio"),
    pathname.startsWith("/meetings"),
    pathname.startsWith("/jobs"),
    pathname.startsWith("/admin"),
  ].some(Boolean);

  if (!protectedPaths) {
    return NextResponse.next(); // публичные страницы
  }

  if (await checkAuth(req)) {
    return NextResponse.next();
  }

  // 3) редиректим на /login с возвратом на исходный путь
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", pathname + (req.nextUrl.search || ""));
  return NextResponse.redirect(url);
}

// матчим /login и защищённые секции
export const config = {
  matcher: ["/login", "/audio/:path*", "/meetings/:path*", "/jobs/:path*", "/admin/:path*"],
};
