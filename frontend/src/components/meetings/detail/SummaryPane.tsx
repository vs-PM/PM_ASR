import * as React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function SummaryPane({ text }: { text: string }) {
  const value = (text ?? '').trim();

  if (!value) {
    return (
      <p className="text-gray-500">
        Протокол пока пуст. Нажмите «Создать протокол», затем «Обновить».
      </p>
    );
  }

  return (
    <div className="prose max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {value}
      </ReactMarkdown>
    </div>
  );
}
