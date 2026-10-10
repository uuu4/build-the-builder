# Durum ve devam notu (2026-10-10, 21:20 TSİ)

Başka bir ortamdan devam etmek için. Ayrıntılı sonuçlar: `docs/olcum-builder-v1.md` (bizim builder), `docs/olcum-brief-a.md` ve `docs/olcum-taban-ab-stil.md` (örnek builder, taban).

## Ne var

| Yol | Ne |
|---|---|
| `builder/build.py` | Bizim builder. `python3 builder/build.py <brief>... [--tools <openapi>] [--slot ad] [--minutes 30]`. Slot varsayılanı `ours-<son brief adı>`. Çıktı: `out/<slot>/`, `submission/<slot>.workflow.json`, `traces/<slot>-<zaman>.{jsonl,log}` |
| `builder/cli.py` | Ajanın çağırdığı araçlar: `spec-doc`, `lint`, `deploy`, `test`, `event` |
| `builder/kit/` | Brief'ten bağımsız parçalar: `front.py` (açılış, kim açtı, üçüncü kişi, kimlik), `ladder.py` (ikna merdiveni + kaydın motorla yeniden denenmesi), `graph.py`, `pycode.py` (takvim, `read_list`, `money`), `openapi.py`, `lint.py`, `deploy.py` |
| `.claude/skills/collections-builder/SKILL.md` | Builder'daki Claude'un skill'i (dersler burada) |
| `builder/tests/` | `python3 -m unittest builder.tests.test_kit` (yerel, ağ yok; sızıntı testi dahil), `front_harness.py` (yalnız ön yarı, Freya'da), `measure.sh` (kur + 3 tekrar + 5 stil) |
| `practice/brief-r/` | Ham banka malzemesi biçiminde deneme brief'i ve cevap anahtarı (`cases.json`) |
| `baseline/example-builder/` | Kit'in örnek builder'ının çıktıları ve izleri |

## Yeni ortamda kurulum

```bash
cp env.example env.sh   # FREYA_API_KEY, FREYA_API_URL, FREYA_BANK_TEAM_KEY (takımın aynı anahtarı)
source env.sh
pip install claude-agent-sdk
python3 -m unittest builder.tests.test_kit
```

`.freya-agents.json` (slot -> workflow eşlemesi) gitignore'da. Yeni ortamda yoksa `save_workflow` aynı slot için **yeni** workflow yaratır. Mevcutları kullanmak için bu içeriği `.freya-agents.json` olarak kaydet:

```json
{
 "brief-a": {"workflow_id": "d8045db7-ae61-48c6-9b1e-2cd16f880335", "agent_id": "e84ca520-d125-4644-8905-7bbbee1c29ce"},
 "brief-b": {"workflow_id": "26d87818-853d-4bdf-9cd9-f61309e01209", "agent_id": "5b9f761c-ea1a-4358-8547-8a84a0b0a79d"},
 "front-test": {"workflow_id": "afaad61b-1b05-47d7-96f2-7909a0ba4b7c", "agent_id": "2d2332c6-eeeb-420f-ac44-712ee6ec3cc1"},
 "ours-brief-a": {"workflow_id": "daff3552-4591-4df9-93e9-cd59e1a0aa43", "agent_id": "33be7c98-303d-44b7-a3c6-fb10290be998"},
 "ours-brief-b": {"workflow_id": "da444e61-4d9f-4d3f-a4ed-9979184165d2", "agent_id": "41163692-a099-4ddf-82bb-eda34adb3acc"},
 "ours-brief-r": {"workflow_id": "c4465e64-d9bf-48a5-aeb7-77ffdcdab336", "agent_id": "ee8ef9d3-a709-4cdb-8992-05cec46d21f9"}
}
```

`results/` (ham ölçüm JSON'ları) de gitignore'da, bu ortamda kaldı; özetleri `docs/` altında.

## Sonuçlar (kısa)

| | Örnek builder | Bizim builder |
|---|---|---|
| Brief A, 3 tekrar, 3/3 kuralı | 8/10 | 9/10 |
| Brief A, 5 stil | 27/50 | 44/50 |
| Brief B vakaları, 3 tekrar | ölçüm yavaşlıktan bozuk | 2/3 |
| Brief R (görülmemiş ham malzeme), 3 tekrar | yok | 9/10 (28/30 arama), stiller 39/50 |

## Açık işler (öncelik sırasıyla)

1. **Çok ürün:** ürün başına ikna merdiveni (PUB-12: deneme sayısı ürün başına tutulmuyor) ve müşterinin tek tarihinin her ürünün son tarihine göre **kodla** düzeltilmesi (PUB-13).
2. **Teklif tekrarı (PUB-06):** aynı tutarın yalnızca tarihi değişiyorsa sadece tarih sorulmalı; skill'e yazıldı, ölçülmedi.
3. Brief R'nin temiz şartname versiyonuyla ikinci genelleme testi; farklı alanlı bir `openapi` ile lint/kurulum denemesi.
4. `docs/interfaces.md` güncellenmeli: sözleşmedeki `rules.json -> compile` yerine ajan kit'i kullanan `out/<slot>/gen.py` yazıyor; S+K (skill, kit) Emre'nin alanı, bu iş Latif'in isteğiyle yapıldı.

## Bilinen platform tuzakları

- Freya'nın Python kutusu (snekbox) bugün iki kez çöktü: kancalı araçlar ve kod düğümleri o sırada düşüyor. Araçlarda kanca yok; kod düğümü bir kez yeniden deneniyor.
- `api_request` düğümünde liste eşlemesi değişkene gelmiyor; `read_list` düzleştirilmiş anahtarları okuyor.
- Model başarısız sözü kendiliğinden yeniden denemiyor; `ladder.py` motorla yeniden gönderiyor.
- Pratik banka `close_call` sebebini A/B listesine göre denetliyor: kendi brief'lerimizde farklı kodlar reddedilir, puanı `close_call` argümanlarından hesapla.
- `/api/v2/chat/message` 502 verip aramaları karıştırabiliyor; test için simülasyon kullan.
- Çalışma alanında aynı anda tek simülasyon; yavaş koşuları `--rerun-if-slow 1` ile at.
