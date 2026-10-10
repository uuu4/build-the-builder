# Ölçüm: kendi builder'ımız, ilk sürüm, Brief A (2026-10-10)

Builder: `python3 builder/build.py briefs/brief-a.md` (kit + `collections-builder` skill'i). Çalışma: 470 sn, 1,01 USD, ajan 19 tur; kendi testlerinde 9/10, düzeltme, 10/10. İz `traces/brief-a-20261010-145902.{jsonl,log}`, çıktılar `out/brief-a/`, `submission/brief-a.workflow.json`.
Ajan: workflow `d8045db7-ae61-48c6-9b1e-2cd16f880335` sürüm 3, agent `e84ca520-d125-4644-8905-7bbbee1c29ce` (slot çakışması: örnek builder'ın slot'u, bkz. `olcum-brief-a.md`).
Bütün koşular `--rerun-if-slow 1` ile; hiçbiri yavaş çıkmadı (en yavaş tur medyanı 1 ile 2 sn), platform arızası yok.

## Örnek builder ile yan yana (Brief A, aynı 10 müşteri)

| Koşul | Örnek builder | Bizim builder |
|---|---|---|
| Stilsiz, 3 tekrar, 3/3 kuralı | 8/10 | **9/10** (koşular 9, 10, 10) |
| `pieces` | 5/10 | **10/10** |
| `corrects` | 9/10 | 8/10 |
| `talkative` | 3/10 | **8/10** |
| `asks_back` | 2/10 (arızalı koşu) | **9/10** |
| `in_words` | 8/10 | **9/10** |
| Stil aramaları toplam | 27/50 | **44/50** |

Ayrıca: ön yarı test düzeneği (`builder/tests/front_harness.py`), 13 müşteri: stilsiz 13/13, `pieces` 12/13, `talkative` 13/13, `asks_back` 13/13.

## Kalan hatalar

| Vaka | Nerede | Ne oldu |
|---|---|---|
| PUB-06 (stilsiz 1 kez, `corrects`, `in_words`) | arka yarı, ikna planı | Tam tutar fazla dendi, asgari ödeme önerildi, müşteri "bugün olmaz" dedi, ajan `no_promise / refused` ile kapattı. Brief'e göre asgarinin reddi düz ret sayılır ve 1. deneme (asgari, haftanın son iş günü) hâlâ yapılmalı. Örnek builder'ın tersine aşırı düzeltme: artık asgariyi ikinci kez önermiyor ama denemeyi de atlıyor. |
| PUB-04 `corrects` | arka yarı | Müşteri tutarı düzeltti, ajan ilk söyleneni (1200) kaydetti, beklenen 1250. |
| PUB-05 `asks_back` | arka yarı, durum sınıflandırma | İş kaybı + indirim isteği `restructuring` sayıldı, devredildi; beklenen `hardship`. |
| PUB-06, PUB-09 `talkative` | simüle müşteri | Müşteri modeli cümleleri yarıda kesti, telefon numarasını hiç söylemedi; ajan doğru şekilde tekrar sordu, 16 turda kimlik düğümünün sınırına geldi. Ajan hatası değil. |

Sıradaki: ikna planını (deneme 1'in tutarı ve tarihi, reddin sayılması) kit'e kod olarak almak; düzeltmeyi ve "kendini düzelten müşteri"yi arka yarı prompt'una genel kural olarak eklemek; Brief B (çok ürün) ile ölçmek.
