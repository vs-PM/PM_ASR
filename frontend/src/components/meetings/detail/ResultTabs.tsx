import * as React from 'react';
import TextPane from './TextPane';
import SegmentsPane from './SegmentsPane';
import SpeakersPane from './SpeakersPane';

type Seg = { id: number; start_ts: number|null; end_ts: number|null; text: string; speaker: string|null; lang: string|null };
type Sp  = { id: number; speaker: string; display_name: string|null; color: string|null; is_active: boolean };

type Props = {
  text: string;
  segments: Seg[];
  speakers: Sp[];
};

export default function ResultTabs({ text, segments, speakers }: Props) {
  const [active, setActive] = React.useState<'text'|'segments'|'speakers'>('text');

  return (
    <>
      <div className="border-b mb-3 flex gap-3 text-sm">
        <button
          className={`px-2 py-1 border-b-2 ${active==='text' ? 'border-black' : 'border-transparent text-gray-500'}`}
          onClick={() => setActive('text')}
        >Текст</button>
        <button
          className={`px-2 py-1 border-b-2 ${active==='segments' ? 'border-black' : 'border-transparent text-gray-500'}`}
          onClick={() => setActive('segments')}
        >Сегменты</button>
        <button
          className={`px-2 py-1 border-b-2 ${active==='speakers' ? 'border-black' : 'border-transparent text-gray-500'}`}
          onClick={() => setActive('speakers')}
        >Спикеры</button>
      </div>

      {active === 'text' && <TextPane text={text} />}
      {active === 'segments' && <SegmentsPane segments={segments} />}
      {active === 'speakers' && <SpeakersPane speakers={speakers} />}
    </>
  );
}
