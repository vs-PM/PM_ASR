import type { Metadata } from "next";
import { Suspense } from "react";
import LoginForm from "./LoginForm";

export const metadata: Metadata = {
  title: "Вход",
  robots: { index: false },
};

type SP = { next?: string };

export default function Page({ searchParams }: { searchParams: SP }) {
  // Безопасный целевой путь: только относительный и с ведущим слешем
  const raw = searchParams?.next ?? "/";
  const nextPath = typeof raw === "string" && raw.startsWith("/") ? raw : "/";

  return (
    <main className="min-h-dvh grid place-items-center p-4">
      {/* Suspense не обязателен, но пусть будет для готовности к асинх. клиент-логике */}
      <Suspense fallback={null}>
        <LoginForm nextPath={nextPath} />
      </Suspense>
    </main>
  );
}
