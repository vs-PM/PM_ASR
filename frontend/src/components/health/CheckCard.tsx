'use client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ReactNode } from 'react';

export function CheckCard({
  title,
  ok,
  message,
  children,
  icon,
}: {
  title: string;
  ok?: boolean;
  message?: string;
  icon?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Card className="border border-gray-200">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          {icon}{title}
        </CardTitle>
        <Badge className={ok ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}>
          {ok ? 'OK' : 'FAIL'}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-2">
        {message && <div className="text-sm text-gray-700 break-words">{message}</div>}
        {children}
      </CardContent>
    </Card>
  );
}
