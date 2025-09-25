"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Props = { nextPath: string };

export default function LoginForm({ nextPath }: Props) {
  const router = useRouter();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Префетчим страницу назначения: быстрее после логина
  useEffect(() => {
    router.prefetch(nextPath);
  }, [nextPath, router]);

  async function doLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);

    // простая клиентская валидация
    if (!u || !p) {
      setErr("Заполните логин и пароль");
      return;
    }

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ username: u.trim(), password: p }),
      });

      if (!res.ok) {
        // можно разобрать тело ответа, если бэк присылает код ошибки
        setErr(res.status === 401 ? "Неверный логин или пароль" : "Ошибка входа");
        return;
      }

      // прогрев профиля (чтоб шапка/меню сразу подхватили авторизацию)
      await fetch("/api/v1/auth/me", { credentials: "include" }).catch(() => {});

      // мягкий переход + инвалидация кэша
      startTransition(() => {
        router.replace(nextPath);
        router.refresh();
      });
    } catch {
      setErr("Сеть недоступна. Проверьте подключение.");
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Вход</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={doLogin} noValidate>
          <div>
            <label htmlFor="login" className="text-sm">Логин</label>
            <Input
              id="login"
              name="login"
              autoComplete="username"
              value={u}
              onChange={(e) => setU(e.target.value)}
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="text-sm">Пароль</label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={p}
              onChange={(e) => setP(e.target.value)}
              required
            />
          </div>

          {err && <p className="text-sm text-red-600">{err}</p>}

          <button
            type="submit"
            disabled={isPending}
            className="w-full inline-flex items-center justify-center rounded-md border px-3 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-60"
            aria-busy={isPending}
          >
            {isPending ? "Входим…" : "Войти"}
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
