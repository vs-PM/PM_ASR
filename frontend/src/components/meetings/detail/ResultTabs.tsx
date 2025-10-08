import * as React from 'react';
import SummaryPane from './SummaryPane';
import SegmentsView from './SegmentsView';
import AudioView from './AudioView';

type Seg = {
  id: number;
  start_ts: number | null;
  end_ts: number | null;
  text: string | null;
  speaker?: string | null;
  lang?: string | null;
};

export type Tab = 'audio' | 'segments' | 'summary';

type Props = {
  // данные
  segments: Seg[];
  modeLabel?: string;
  status: string;         // queued | diarize_done | transcription_done | summary_processing | summary_done
  summaryText?: string;   // текст протокола

  // управление
  active?: Tab;
  onChange?: (t: Tab) => void;
  onRefreshSummary?: () => void;
};

export default function ResultTabs(props: Props) {
  const [active, setActive] = React.useState<Tab>(props.active ?? 'audio');

  React.useEffect(() => {
    if (props.active && props.active !== active) setActive(props.active);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.active]);

  const go = (t: Tab) => {
    setActive(t);
    props.onChange?.(t);
  };

  const tabBtn = (key: Tab, label: string) => (
    <button
      key={key}
      className={`px-2 py-2 -mb-px border-b-2 ${active===key ? 'border-black font-medium' : 'border-transparent text-gray-500 hover:text-black'}`}
      onClick={() => go(key)}
    >
      {label}
    </button>
  );

  return (
    <>
      <div className="border-b mb-3 flex gap-3 text-sm items-center">
        {tabBtn('audio', 'Аудио')}
        {tabBtn('segments', 'Сегменты')}
        {tabBtn('summary', 'Протокол')}

        {active === 'summary' && (
          <div className="ml-auto">
            <button
              onClick={props.onRefreshSummary}
              className="text-xs px-2 py-1 border rounded hover:bg-gray-50"
              title="Обновить протокол"
            >
              Обновить
            </button>
          </div>
        )}
      </div>

      {active === 'audio' && (
        <AudioView modeLabel={props.modeLabel} segments={props.segments} />
      )}

      {active === 'segments' && (
        <SegmentsView
          status={props.status}
          modeLabel={props.modeLabel}
          segments={props.segments}
        />
      )}

      {active === 'summary' && <SummaryPane text={props.summaryText || ''} />}
    </>
  );
}
