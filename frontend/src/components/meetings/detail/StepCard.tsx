import * as React from 'react';

type Props = {
  title: string;
  helper?: string;
  right?: React.ReactNode;
  children?: React.ReactNode;
};

export default function StepCard({ title, helper, right, children }: Props) {
  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        {right}
      </div>
      {helper && <p className="text-xs text-gray-500 mb-2">{helper}</p>}
      <div className="flex gap-2 flex-wrap">{children}</div>
    </div>
  );
}
