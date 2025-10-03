import * as React from 'react';

type Props = { text: string };

export default function TextPane({ text }: Props) {
  const [q, setQ] = React.useState('');
  const rx = React.useMemo(() => {
    try { return q ? new RegExp(q, 'ig') : null; } catch { return null; }
  }, [q]);

  const highlighted = React.useMemo(() => {
    if (!rx || !text) return [text];
    const out: React.ReactNode[] = [];
    let lastIndex = 0;
    for (;;) {
      const m = rx.exec(text);
      if (!m) break;
      out.push(text.slice(lastIndex, m.index));
      out.push(<mark key={m.index} className="bg-yellow-200">{m[0]}</mark>);
      lastIndex = m.index + m[0].length;
      if (!rx.global) break;
    }
    out.push(text.slice(lastIndex));
    return out;
  }, [text, rx]);

  return (
    <div>
      <div className="mb-2 flex gap-2 items-center">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск по тексту…"
          className="border rounded px-2 py-1 w-full"
        />
        <button
          onClick={() => navigator.clipboard.writeText(text)}
          className="px-2 py-1 border rounded hover:bg-gray-50"
        >
          Копировать
        </button>
      </div>

      {text ? (
        <div className="prose max-w-none whitespace-pre-wrap">{highlighted}</div>
      ) : (
        <p className="text-sm text-gray-500">Текста пока нет. Заверши транскрипцию.</p>
      )}
    </div>
  );
}
