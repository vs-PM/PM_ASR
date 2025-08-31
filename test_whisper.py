import sys
import torch
from faster_whisper import WhisperModel

def load_whisper_model(model_size="Large-v3"):
    """
    Загружает модель Whisper со стратегией fallback:
    1️ float16 (быстро, если работает)
    2️ int8_float16 (рекомендовано для L4/T4)
    3️ int8 (максимальная стабильность, но медленнее)
    """
    candidates = ["float16", "int8_float16", "int8"]

    for ctype in candidates:
        try:
            print(f"🔄 Пытаюсь загрузить модель '{model_size}' c compute_type={ctype}...")
            model = WhisperModel(model_size, device="cuda", compute_type=ctype)

            if torch.cuda.is_available():
                # warm-up CUDA
                _ = torch.randn(1).to("cuda")
                torch.cuda.synchronize()
            print(f"✅ Успешно загружено с compute_type={ctype}")
            return model

        except Exception as e:
            print(f"❌ Не удалось загрузить с compute_type={ctype}: {e}")
            continue

    raise RuntimeError("Ни один compute_type не сработал!")


def main(audio_file: str):
    print("=== Проверка CUDA ===")
    print("CUDA available:", torch.cuda.is_available())
    print("CUDA version:", torch.version.cuda)
    print("cuDNN version:", torch.backends.cudnn.version())

    # грузим модель с fallback
    model = load_whisper_model("small")

    print(f"▶️ Начинаю транскрипцию файла: {audio_file}")
    try:
        segments, info = model.transcribe(audio_file, beam_size=5, language="ru")

        print("### Инфо по аудио ###")
        print(info)

        print("\n### Расшифровка ###")
        for i, seg in enumerate(segments, start=1):
            print(f"[{i}] {seg.start:.2f}s → {seg.end:.2f}s: {seg.text}")

    except Exception as e:
        print("❌ Ошибка в процессе транскрипции:", e)
        raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_whisper_stable.py <path-to-audio>")
        sys.exit(1)
    main(sys.argv[1])