import * as React from 'react';
import { useMeetingBundle } from '@/hooks/useMeetingBundle';
import { useStartEmbedSum, useSummary } from '@/hooks/useSummary';
import Header from './Header';
import ResultTabs, { Tab } from './ResultTabs';
import StepCard from './StepCard';
import ModeSelector from './ModeSelector';

type Props = { meetingId: number };

function decideInitialTab(status: string | undefined, segmentsCount: number): Tab {
  if (status === 'summary_done' || status === 'summary_processing') return 'summary';
  if (segmentsCount > 0) return 'segments';
  return 'audio';
}

export default function MeetingScreen({ meetingId }: Props) {
  const b = useMeetingBundle(meetingId);

  // хуки — безусловно
  const startES = useStartEmbedSum();
  const transcriptId = b.v2.data?.transcript_id ?? null;

  // поллинг выключен (в тестах): 4-й аргумент = false
  const sum = useSummary(transcriptId, b.mode, Boolean(transcriptId), false);

  // рассчитанный статус режима
  const status = sum.data?.status ?? b.globalStatus ?? 'queued';
  const creatingNow = startES.isPending || status === 'summary_processing';
  const summaryText = sum.data?.text ?? '';

  // сегменты текущего режима (ожидаем, что в v2 уже под текущий mode)
  const segments = b.v2.data?.segments ?? [];
  const segmentsCount = segments.length;

  // вкладка и контроль авто-режима
  const [activeTab, setActiveTab] = React.useState<Tab>('audio');
  const [autoModeKey, setAutoModeKey] = React.useState<string>(b.mode); // для кого последний auto выбор
  const manualRef = React.useRef(false); // пользователь менял вкладку руками?

  // пользователь сменил вкладку → фиксируем ручной режим, чтобы не перетирало
  const onTabChange = (t: Tab) => {
    manualRef.current = true;
    setActiveTab(t);
  };

  // смена режима: делаем детерминированный первичный выбор и разрешаем ОДИН апгрейд
  React.useEffect(() => {
    // новый режим → сбрасываем «ручной» флаг и выбираем вкладку по текущим данным
    manualRef.current = false;
    const initial = decideInitialTab(sum.data?.status, segmentsCount);
    setActiveTab(initial);
    setAutoModeKey(b.mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b.mode]);

  // апгрейд до «summary», когда статус подтверждён (и только для «своего» режима)
  React.useEffect(() => {
    if (manualRef.current) return;          // пользователь уже выбирал — не трогаем
    if (autoModeKey !== b.mode) return;     // на всякий случай
    if (activeTab === 'summary') return;    // уже там

    if (status === 'summary_done' || status === 'summary_processing') {
      setActiveTab('summary');
    }
  }, [status, b.mode, autoModeKey, activeTab]);

  // обработчик без useCallback
  const handleCreateProtocol = () => {
    if (!transcriptId) return;
    startES.mutate(
      { id: transcriptId, mode: b.mode },
      {
        onSuccess: () => {
          setActiveTab('summary');
          setTimeout(() => sum.refetch(), 800);
        },
      }
    );
  };

  // ранние возвраты
  if (b.meeting.isLoading || b.summary.isLoading) return <p>Загрузка…</p>;
  if (b.meeting.isError) return <div className="text-red-600">Ошибка: {b.meeting.error?.message}</div>;
  if (!b.meeting.data) return <p>Не найдено</p>;

  const meta = b.meeting.data;
  const displayId = meetingId;

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      {/* Левая колонка: шаги */}
      <div className="lg:col-span-1 space-y-4">
        <Header
          title={`Митинг #${displayId}`}
          meetingId={displayId}
          filename={meta.filename ?? '—'}
          createdAt={meta.created_at ?? null}
          status={creatingNow ? 'summary_processing' : b.globalStatus}
          progress={meta.job?.progress ?? null}
        />

        {/* Шаг 1: Нарезка */}
        <StepCard
          title="Шаг 1: Нарезка"
          helper="Нарезка выполняется отдельно для каждого режима. Если чанки уже есть — повторная нарезка не запускается."
          right={<span className="text-xs text-gray-500">Режим: <b>{b.mode}</b></span>}
        >
          <button
            onClick={b.startCut}
            className="px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
            disabled={!b.canCut || b.cuttingNow}
          >
            {b.cuttingNow ? 'Режу…' : 'Нарезать выбранный режим'}
          </button>
        </StepCard>

        {/* Шаг 2: Транскрипция */}
        <StepCard
          title="Шаг 2: Транскрипция"
          helper="Запускается по выбранному режиму. Готовые сегменты пропускаются."
        >
          <button
            onClick={b.startTranscribe}
            className="px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
            disabled={!b.canTranscribe || b.transcribingNow}
          >
            {b.transcribingNow ? 'Транскрибирую…' : 'Транскрибировать по выбранному режиму'}
          </button>
        </StepCard>

        {/* Шаг 3: Протокол */}
        <StepCard
          title="Шаг 3: Протокол"
          helper="Формирует эмбеддинги для выбранного режима и создаёт протокол (RAG). Результат во вкладке «Протокол»."
        >
          <button
            onClick={handleCreateProtocol}
            className="px-3 py-2 border rounded-md hover:bg-gray-50 disabled:opacity-60"
            disabled={!transcriptId || creatingNow || status !== 'transcription_done'}
            title={status !== 'transcription_done' ? 'Сначала завершите транскрипцию выбранного режима' : undefined}
          >
            {creatingNow ? 'Создаю протокол…' : 'Создать протокол'}
          </button>
          <button
            onClick={() => { setActiveTab('summary'); sum.refetch(); }}
            className="px-3 py-2 border rounded-md hover:bg-gray-50"
          >
            Показать / обновить протокол
          </button>
        </StepCard>
      </div>

      {/* Правая колонка: выбор режима + результат */}
      <div className="lg:col-span-2 border rounded-lg p-4 bg-white">
        <div className="mb-3">
          <ModeSelector
            mode={b.mode}
            onChange={(m) => {
              b.setMode(m);
              // вкладка определяется автоматически в useEffect выше
            }}
          />
        </div>

        <div className="flex items-center justify-between mb-2">
          <h2 className="font-medium">Результат</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs px-2 py-1 rounded border">Режим: <b>{b.mode}</b></span>
            <span className="text-xs px-2 py-1 rounded border">{status}</span>
          </div>
        </div>

        <ResultTabs
          segments={segments}
          modeLabel={b.mode}
          status={status}
          summaryText={summaryText}
          active={activeTab}
          onChange={onTabChange}
          onRefreshSummary={() => sum.refetch()}
        />
      </div>
    </div>
  );
}
