import Link from "next/link";

export default function Landing() {
  return (
    <section className="relative overflow-hidden">
      {/* мягкий светлый фон с акцентным пятном */}
      <div className="pointer-events-none absolute inset-0 opacity-80
        [background:radial-gradient(50%_35%_at_80%_10%,_#ffe9e0_0,_transparent_60%),radial-gradient(45%_35%_at_10%_85%,_#f6f6f6_0,_transparent_60%)]" />
      <div className="relative mx-auto max-w-5xl px-6 py-20">
        <div className="mb-8 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-neutral-600 shadow-sm bg-white/70">
          Внутренний сервис Melon Fashion
        </div>
        <h1 className="text-4xl md:text-6xl font-semibold leading-[1.1] tracking-tight text-neutral-900">
          Протокол из аудио — быстро, аккуратно, по делу
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-neutral-600">
          Загрузите запись встречи — система распознает речь, разметит участников,
          выделит решения и задачи, и подготовит удобный протокол.
        </p>

        <div className="mt-10 flex items-center gap-4">
          <Link
            href="/login?next=/"
            className="rounded-2xl px-5 py-3 text-sm font-medium bg-black text-white shadow hover:opacity-90"
          >
            Войти и начать
          </Link>
        </div>

        <div className="mt-14 grid gap-6 sm:grid-cols-3">
          {[
            ["Точность", "ASR, diarization и пост-обработка."],
            ["Структура", "Решения, задачи, теги, таймкоды."],
            ["Интеграции", "Jira / YouTrack / Notion, экспорт Markdown."],
          ].map(([t, d]) => (
            <div key={t} className="rounded-2xl border p-5 bg-white/80 shadow-[0_1px_0_rgba(0,0,0,0.05)]">
              <div className="text-sm font-semibold">{t}</div>
              <div className="mt-1 text-sm text-neutral-600">{d}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
