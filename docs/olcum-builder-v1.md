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

## v2: ikna merdiveni (aynı gün, 19:00 TSİ)

Değişiklik: `builder/kit/ladder.py`, her teklif bir düğüm; ret, "çok fazla" ve bant koşulu extraction + kesin rota. Builder: `python3 builder/build.py briefs/brief-a.md` (slot `ours-brief-a`, workflow `daff3552-4591-4df9-93e9-cd59e1a0aa43`, agent `33be7c98-303d-44b7-a3c6-fb10290be998`), 961 sn, 0,95 USD. İlk testte 2/10: hesap kodu ürün listesini okuyamadı (liste eşlemesi değişkene gelmiyor, yalnızca düzleştirilmiş anahtarlar geliyor); ajan düzeltti, 10/10. Bu okuma sonra kit'e alındı (`read_list`).

| Koşul | Örnek builder | v1 | v2 |
|---|---|---|---|
| Stilsiz, 3 tekrar, 3/3 kuralı | 8/10 | 9/10 | 9/10 (PUB-06 1/3) |
| `pieces` | 5/10 | 10/10 | 8/10 |
| `corrects` | 9/10 | 8/10 | 9/10 |
| `talkative` | 3/10 | 8/10 | 8/10 |
| `asks_back` | 2/10 | 9/10 | 9/10 |
| `in_words` | 8/10 | 9/10 | 10/10 |
| Stil toplamı | 27/50 | 44/50 | 44/50 |

Kalan hatalar:
- PUB-06 (4 arama): merdiven doğru çalışıyor (ret sayılıyor, 1. deneme yapılıyor, söz doğru), ama ajan asgari ödemeyi önce "bugün", sonra "Cuma" diye iki kez söylüyor; değerlendirici bunu iki teklif sayıyor. Skill'e kural eklendi: aynı tutarın yalnızca tarihi değişiyorsa sadece tarih sorulur; düşük tutar teklifi bir güne bağlanmaz.
- PUB-03 `pieces`/`corrects`, PUB-06 `talkative`: simüle müşteri cümleleri yarıda kesiyor, cevabı hiç tamamlamıyor.
- PUB-05 `talkative`: hardship yolu, incelenecek.

Not: stil koşuları birer tekrar; 10 aramada 1 ile 2 aramalık fark gürültü sınırında.

## 2. adım: Brief A + B (çok ürün)

`python3 builder/build.py briefs/brief-a.md briefs/brief-b.md` (slot `ours-brief-b`, agent `41163692-a099-4ddf-82bb-eda34adb3acc`): 461 sn, 0,72 USD. Yalnızca B vakaları ölçüldü (A vakaları B'nin not kuralı yüzünden bu ajan için geçerli sınav değil).

| Koşul | Sonuç |
|---|---|
| 3 tekrar, 3/3 kuralı | 2/3 (PUB-11 3/3, PUB-12 2/3, PUB-13 3/3) |
| Stiller (her biri 3 arama) | `pieces` 2, `corrects` 1, `talkative` 1, `asks_back` 3, `in_words` 2: toplam 9/15 |

Hatalar: PUB-12 ürün başına deneme sayısı aşılıyor (merdiven çok ürüne uygulanmamış, sayma prompt'ta). PUB-13 tek tarihin ürün başına son tarihe göre düzeltilmesi modele kalmış, kredi 30 Ekim'e kaydediliyor (doğrusu 23). İkisi de kit'e alınacak: ürün başına merdiven ve ürün başına tarih düzeltmesinin kodda yapılması.

## 3. adım: Brief R (görülmemiş, ham banka malzemesi)

`practice/brief-r/brief-r.md`: mail + politika + memo + kod listesi; banka adı, soru sırası, tatiller, bantlar, geri arama saatleri ve bütün sebep kodları A'dan farklı. Builder (slot `ours-brief-r`, agent `ee8ef9d3-a709-4cdb-8992-05cec46d21f9`): **148 sn, 0,76 USD, kendi testi yok** (pratik bankada bu brief'in vakası yok, finaldeki durum gibi).

Ölçüm notu: pratik banka `close_call` sebebini A/B listesine göre denetliyor ve R'nin kodlarını (`cb_booked`, `restructure`...) reddediyor. Bu yüzden puan, ajanın `close_call`'a gönderdiği değerlerle yeniden hesaplandı (`practice/brief-r/cases.json` cevap anahtarı); hakem (konuşma) hataları olduğu gibi sayıldı.

| Koşul | Sonuç |
|---|---|
| 3 tekrar | 28/30 arama; 3/3 kuralıyla 9/10 (PUB-10 1/3) |
| Stiller | `pieces` 7, `corrects` 8, `talkative` 6, `asks_back` 9, `in_words` 9: toplam 39/50 |

Builder ham malzemeden doğru okudu: bütün sebep kodları, ters soru sırası (önce telefon), memonun üç değişikliği (6. iş günü, 17:00, "iki iş günü"), yeni tatiller ve bant sınırları.

Sistematik hata PUB-10: ilk kayıt başarısız olunca model yeniden denemedi ("bir sorun oldu" deyip devam etti). Düzeltme kit'te: `ladder.py` başarısız sözü motorun kendisi aynı argümanlarla (`{{create_promise_args.*}}`) bir kez daha gönderiyor. Brief A ajanında doğrulandı: PUB-10 3/3, ikinci çağrıda tutar sayı olarak gitti ve kayıt tuttu.
