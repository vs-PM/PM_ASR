"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import LogoutButton from "./LogoutButton";

export type Me =
  | {
      user: { id: number; login: string; role: string };
    }
  | null;

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link
      href={href}
      className={`px-3 py-2 rounded-md text-sm font-medium ${
        active ? "bg-black text-white" : "text-black hover:bg-gray-100"
      }`}
    >
      {children}
    </Link>
  );
}

export function Header({ me }: { me: Me }) {
  const displayName = me?.user?.login ?? (me?.user?.id ? `#${me.user.id}` : "");

  return (
    <header className="border-b">
      <div className="mx-auto max-w-6xl px-4 h-14 flex items-center justify-between">
        <nav className="flex items-center gap-1">
          <NavLink href="/">Home</NavLink>
          {me ? (
            <>
              <NavLink href="/audio">Аудио</NavLink>
              <NavLink href="/meetings">Митинги</NavLink>
              <NavLink href="/jobs">Задачи</NavLink>
              <NavLink href="/admin">Админ</NavLink>
            </>
          ) : null}
        </nav>

        <div className="flex items-center gap-3">
          {me ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{displayName}</span>
              <LogoutButton />
            </div>
          ) : (
            <Link href="/login" className="px-3 py-1 border rounded-md hover:bg-gray-50 text-sm">
              Войти
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
