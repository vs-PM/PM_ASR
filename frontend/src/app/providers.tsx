'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';


let _client: QueryClient | null = null;
function getClient() {
  if (_client) return _client;
  _client = new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
  return _client;
}


export default function Providers({ children }: { children: React.ReactNode }) {
  const client = React.useMemo(() => getClient(), []);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}