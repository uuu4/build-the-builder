# Taban ölçümü 2: örnek builder, Brief A+B ve konuşma stilleri (kit v3, 2026-10-10)

İlk ölçüm (`docs/olcum-brief-a.md`): örnek builder'ın Brief A ajanı, 3 tekrar, 3/3 kuralıyla 8/10.

## 1. Brief A+B ajanı

`python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md`, skill değiştirilmeden.

| | |
|---|---|
| workflow_id / agent_id | `26d87818-853d-4bdf-9cd9-f61309e01209` / `5b9f761c-ea1a-4358-8547-8a84a0b0a79d` (slot `brief-b`) |
| Builder | 1158 sn, 33 tur, 2,07 USD. Üreteç `baseline/example-builder/gen_brief_b.py`, iz `baseline/example-builder/20261010-132017.jsonl` |
| Builder'ın kendi ölçümü | yalnızca B vakaları, 3 tekrar: 9/9. Arada PUB-12 ve PUB-13 için bir düzeltme turu |

Bizim ölçümümüz: 13 vaka, 3 tekrar.

| Koşu | Geçen | En yavaş ajan turu (medyan) | Müşterinin kapattığı başarısız arama |
|---|---|---|---|
| 1 | 3/13 | **300 sn** | 8 |
| 2 | 2/13 | **122 sn** | 10 |
| 3 | 10/13 | 6 sn | 0 |

3/3 kuralıyla 1/13 çıktı, ama bu sayı ajanı ölçmüyor:
- Koşu 1 ve 2'de platform modeli dakikalarca cevap vermedi, müşteriler kapattı. README'nin dediği durum bu: aynı ajan sonraki koşuda hızlıysa düşük puan bizim değil. Organizatörler böyle bir koşuyu atıp tekrarlıyor (`--rerun-if-slow`).
- A vakaları bu ajan için geçerli sınav değil: Brief B ürün başına not istiyor, A vakaları not beklemiyor. Koşu 3'teki PUB-05 ve PUB-08 hataları yalnızca bu notlar.
- Normal hızdaki koşu 3'te gerçek hata tek: **PUB-13**. İki ürünün son tarihleri birbirine karıştı (kart 20 Ekim, kredi 30 Ekim kaydedildi; beklenen 30 ve 23 Ekim), ardından ajan `negotiate` düğümünde tur sınırına kadar döngüye girdi ve `close_call` hiç çalışmadı.

## 2. Brief A ajanı, konuşma stilleri (her stil 1 koşu)

Ajan `e84ca520-d125-4644-8905-7bbbee1c29ce`, `run_cases.py --brief A --style <stil>`.

| Stil | Geçen | Başarısız |
|---|---|---|
| (stilsiz, 3 tekrar) | 8/10 | PUB-06, PUB-10 |
| `corrects` | 9/10 | PUB-10 |
| `in_words` | 8/10 | PUB-06, PUB-10 |
| `pieces` | 5/10 | PUB-03, 04, 08, 09, 10 |
| `talkative` | 3/10 | PUB-03, 04, 05, 06, 07, 09, 10 |
| `asks_back` | 2/10 | PUB-01, 02, 03, 04, 05, 06, 09, 10 |

Koşu hızları normaldi (medyan 4 ile 22 sn), müşterinin kapattığı başarısız arama yok.

**Düzeltme (aynı gün, aramaların olay kaydı okununca):** bazı koşularda Freya'nın Python kutusu (snekbox) ya da bankanın sahte API'si çöktü. Kod adımları, kancalı araçlar ve `close_call` "Failed to reach snekbox" ya da "Cloudflare Tunnel error 1033" ile düştü. Etkilenen aramalar:

| Koşu | Başarısız | Arızadan etkilenen başarısız arama |
|---|---|---|
| A, 3 tekrar | 2 / 1 / 0 | yok |
| `pieces` | 5 | 2 (PUB-09, 10) |
| `corrects` | 1 | 1 (PUB-10) |
| `talkative` | 7 | yok |
| `asks_back` | 8 | **7** (10 aramanın 9'u arızalı) |
| `in_words` | 2 | yok |
| A+B koşu 1 | 10 | 8 (banka API'si kapalı + model yavaş) |
| A+B koşu 2 | 11 | yok (model yavaş) |

Yani `asks_back`'in 2/10'u ölçüm değil, yeniden koşulmalı. `talkative` (7 gerçek hata) ve `pieces` (3 gerçek hata) gerçek zayıflık.

## 3. Hataların türleri

Tek tek hatalardan çıkan tekrar eden kalıplar, sıklık sırasıyla:

1. **Kimlik adımı insan gibi konuşmaya dayanmıyor (9 arama).** Soru soran (`asks_back`), konu dağıtan (`talkative`) ya da numarayı ikiye bölen (`pieces`) müşteri ret sayılıp `not_verified / declined` ile kapatılıyor, ya da yarım cevap yanlış cevap sayılıyor (PUB-03 `pieces`: altı yarım cevaptan sonra kapandı, `talkative`: iki yanlıştan sonra). Brief'in 15. kuralı yalnızca "aramanın ne hakkında olduğunu sormayı" ret sayıyor; "neden soruyorsunuz?" bir ret değil.
2. **`close_call` hiç çalışmıyor.** Olay kaydına bakınca nedenlerin çoğu platform: `close_call` arama sonunda çalışan bir yaşam döngüsü aracı ve üstünde bir Python kancası var. Kutu çökünce kanca, kanca düşünce `close_call` düşüyor; yeniden deneme yok. Kalan tek mantık hatası A+B PUB-13 (düğüm döngüsü). Ders: kritik yazma araçlarını (`close_call`, `create_promise`) Python kancasına bağlamamak.
3. **PUB-10'da "recorded" kelimesi (5 ölçümün 4'ünde).** Vakanın kontrolü harfiyen "agent does not say 'recorded' before a successful call". Açılıştaki zorunlu "this call is recorded" cümlesi buna takılıyor. Gürültü değil, sistematik. Kayıt bilgisini "recorded" kelimesi geçmeden vermek (örneğin "we keep a recording of this call") bu çatışmayı kaldırır.
4. **İkna denemesinde tutar ve sıra (PUB-06, 3 ölçümde).** Tam tutarı reddeden müşteriye 1. denemede yeniden tam tutar öneriliyor, asgari ödeme ikinci kez anılıyor; `in_words`'te söz yanlış tarihe (23 Ekim) kaydedildi.
5. **Söylenene yanlış anlam verme.** `talkative` PUB-04'te sohbet "zaten ödedim" sanıldı (`paid`), PUB-09'da yapılandırma isteği kaçırıldı. `asks_back` PUB-01'de söz **2024-05-24** tarihine kaydedildi: model yılı uydurdu, `create_promise`'tan önce tarihi kodla denetleyen bir adım yok.

## 4. Kendi builder'ımız için çıkanlar

- Asıl kayıp stillerde: temiz müşteride 8/10 olan ajan `talkative` ve `asks_back`'te 2 ile 3'e düşüyor. Final müşterileri bu stillerde konuşacak.
- Kimlik adımı, kapanış garantisi ve `create_promise` öncesi kod denetimi (tarih yılı, pencere, tutar) skill'e değil omurgaya ait: her brief'te aynı şekilde lazım.
- Ölçüm yöntemi: koşu yavaşsa (medyan > 10 sn) sonucu atıp tekrarlamak gerekiyor (`--rerun-if-slow 1`), yoksa ajanı değil platformu ölçüyoruz.
