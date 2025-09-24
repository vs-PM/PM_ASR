"use client";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? process.env.AUTH_API_BASE ?? "";
const api = (p: string) => (API_BASE ? `${API_BASE}${p}` : p);

export default function LogoutClient() {
  const router = useRouter();
  async function onClick() {
    try {
      await fetch(api("/api/v1/auth/logout"), { method: "POST", credentials: "include" });
    } finally {
      router.replace("/login?next=/");
      router.refresh();
    }
  }
  return (
    <button type="button" onClick={onClick} className="rounded-xl border px-3 py-1.5 text-sm hover:bg-gray-100">
      Выйти
    </button>
  );
}
