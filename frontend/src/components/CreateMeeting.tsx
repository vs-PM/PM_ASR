"use client";

import React, { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? process.env.AUTH_API_BASE ?? "";

type FileRow = {
  id: number;
  filename: string;
  size_bytes?: number;
  mimetype?: string;
  created_at?: string;
};

export default function CreateMeeting() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [tab, setTab] = useState<"upload" | "existing">("upload");

  // upload state
  const [file, setFile] = useState<File | null>(null);
  const [uploadPct, setUploadPct] = useState<number>(0);

  // existing files state
  const [files, setFiles] = useState<FileRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [listLoading, setListLoading] = useState(false);

  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (tab === "existing") {
      void loadFiles();
    }
  }, [tab]);

  async function loadFiles() {
    if (!API_BASE) return;
    try {
      setListLoading(true);
      const r = await fetch(`${API_BASE}/api/v1/files?limit=50&offset=0`, {
        credentials: "include",
      });
      if (r.status === 401) {
        setErr("Сессия истекла. Войдите заново.");
        return;
      }
      if (!r.ok) {
        setErr("Не удалось получить список файлов");
        return;
      }
      const data = (await r.json()) as { items?: FileRow[] } | FileRow[];
      const items = Array.isArray(data) ? data : data.items ?? [];
      setFiles(items);
    } catch {
      setErr("Сеть недоступна. Проверьте подключение.");
    } finally {
      setListLoading(false);
    }
  }

  async function uploadFileGetId(localFile: File): Promise<number> {
    return new Promise<number>((resolve, reject) => {
      const url = `${API_BASE}/api/v1/files`;
      const fd = new FormData();
      fd.append("file", localFile);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.withCredentials = true;

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          setUploadPct(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onerror = () => reject(new Error("upload_error"));
      xhr.onload = () => {
        if (xhr.status === 401) return reject(new Error("unauthorized"));
        if (xhr.status === 413) return reject(new Error("too_large"));
        if (xhr.status < 200 || xhr.status >= 300)
          return reject(new Error(`http_${xhr.status}`));
        try {
          const resp = JSON.parse(xhr.responseText) as { id?: number };
          if (typeof resp.id === "number") resolve(resp.id);
          else reject(new Error("bad_response"));
        } catch {
          reject(new Error("bad_json"));
        }
      };

      xhr.send(fd);
    });
  }

  async function createTranscript(file_id: number): Promise<number> {
    const body = {
      title: title.trim(),
      meeting_id: 1, // при желании подставь реальный meeting_id
      file_id,
    };
    const r = await fetch(`${API_BASE}/api/v1/transcripts`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    if (r.status === 401) throw new Error("unauthorized");
    if (!r.ok) throw new Error(`http_${r.status}`);
    const data = (await r.json()) as { transcript_id?: number; id?: number };
    const tid = data.transcript_id ?? data.id;
    if (typeof tid !== "number") throw new Error("bad_response");
    return tid;
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setOkMsg(null);
    setUploadPct(0);

    if (!API_BASE) {
      setErr("API_BASE не задан. Проверь переменные окружения.");
      return;
    }
    if (!title.trim()) {
      setErr("Укажите название встречи");
      return;
    }

    try {
      let fileId: number | null = null;

      if (tab === "upload") {
        if (!file) {
          setErr("Приложите аудиофайл");
          return;
        }
        fileId = await uploadFileGetId(file);
      } else {
        if (!selectedId) {
          setErr("Выберите файл из списка");
          return;
        }
        fileId = selectedId;
      }

      const tid = await createTranscript(fileId);
      setOkMsg("Митинг создан. Идёт обработка…");

      startTransition(() => {
        router.replace(`/transcripts/${tid}`);
        router.refresh();
      });
    } catch (e: unknown) {
      const code = e instanceof Error ? e.message : "unknown";
      const msg =
        code === "too_large"
          ? "Файл слишком большой (413). Увеличьте лимит на сервере."
          : code === "unauthorized"
          ? "Сессия истекла. Войдите заново."
          : "Не удалось создать протокол";
      setErr(msg);
    }
  }

  const prettySize = (n?: number) =>
    typeof n === "number" ? `${(n / (1024 * 1024)).toFixed(1)} MB` : "";

  return (
    <section className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8">
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
          Новый митинг
        </h1>
        <p className="mt-2 text-neutral-600">
          Загрузите аудио или выберите уже загруженное, затем создайте протокол.
        </p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Создать протокол</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={onSubmit} noValidate>
            <div>
              <label htmlFor="title" className="text-sm">
                Название
              </label>
              <Input
                id="title"
                name="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Например: Еженедельный синк WMS, 22.09"
                required
              />
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => setTab("upload")}
                className={`px-3 py-1.5 rounded-xl border ${
                  tab === "upload"
                    ? "bg-black text-white"
                    : "hover:bg-gray-100"
                }`}
              >
                Загрузить файл
              </button>
              <button
                type="button"
                onClick={() => setTab("existing")}
                className={`px-3 py-1.5 rounded-xl border ${
                  tab === "existing"
                    ? "bg-black text-white"
                    : "hover:bg-gray-100"
                }`}
              >
                Выбрать из загруженных
              </button>
            </div>

            {tab === "upload" ? (
              <div>
                <label htmlFor="file" className="text-sm">
                  Аудиофайл
                </label>
                <Input
                  id="file"
                  name="file"
                  type="file"
                  accept="audio/*,.m4a,.mp3,.wav,.ogg,.aac"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  required
                />
                {uploadPct > 0 && uploadPct < 100 && (
                  <p className="mt-1 text-xs text-neutral-600">
                    Загрузка: {uploadPct}%
                  </p>
                )}
                <p className="mt-1 text-xs text-neutral-500">
                  Поддерживаются .m4a, .mp3, .wav и др. Ограничение зависит от
                  сервера.
                </p>
              </div>
            ) : (
              <div>
                <div className="mb-2 text-sm">Мои файлы</div>
                <div className="max-h-64 overflow-auto rounded-xl border">
                  {listLoading ? (
                    <div className="p-3 text-sm text-neutral-600">
                      Загрузка списка…
                    </div>
                  ) : files.length === 0 ? (
                    <div className="p-3 text-sm text-neutral-600">
                      Список пуст. Переключитесь на вкладку «Загрузить файл».
                    </div>
                  ) : (
                    <ul className="divide-y">
                      {files.map((f) => (
                        <li
                          key={f.id}
                          className={`p-3 text-sm cursor-pointer ${
                            selectedId === f.id
                              ? "bg-gray-100"
                              : "hover:bg-gray-50"
                          }`}
                          onClick={() => setSelectedId(f.id)}
                        >
                          <div className="font-medium">{f.filename}</div>
                          <div className="text-neutral-500">
                            {prettySize(f.size_bytes)}{" "}
                            {f.mimetype ? `• ${f.mimetype}` : ""}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {err && <p className="text-sm text-red-600">{err}</p>}
            {okMsg && <p className="text-sm text-green-600">{okMsg}</p>}

            <button
              type="submit"
              disabled={isPending}
              className="w-full inline-flex items-center justify-center rounded-2xl border px-4 py-2.5 text-sm font-medium hover:bg-gray-100 disabled:opacity-60"
              aria-busy={isPending}
            >
              {isPending ? "Создаём…" : "Создать протокол"}
            </button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
