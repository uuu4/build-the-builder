# Çok ürün kiti (multi.py) canlı ölçümü ve R2 kurulumu (2026-10-10, 22:15 TSİ)

Koşan: Latif'in ajanı, bulut ortamı (bankaya erişiyor). Ham sonuçlar: `results/multi-b-1.json`, `results/multi-a-1.json` (gitignore'da, bu ortamda).

## Sonuçlar

| Ölçüm | Ajan | Sonuç (3 tekrar, 3/3 kuralı) | Önceki (ladder.py) |
|---|---|---|---|
| Brief B, PUB-11..13 | `multi-b` f6db8c67 (sürüm 3) | **1/3**: PUB-11 3/3, PUB-12 0/3, PUB-13 2/3 | 2/3: PUB-11 3/3, PUB-12 2/3, PUB-13 3/3 |
| Brief A, PUB-01..10 | `multi-a` 78238d4f | **7/10**: PUB-01 0/3, PUB-04 1/3, PUB-06 2/3 | 9/10 |
| Brief R2, kurulum | `ours-r2` bb854938 | 125 sn, 141 düğüm, lint temiz; 12/12 vakada ürün sırası, son tarih ve deneme sayısı cevap anahtarıyla aynı; 14 kapanış kodu doğru | ilk kez |

R2 canlı ölçülemiyor: pratik banka R2 vaka numaralarını tanımıyor (`unknown practice case`).

## Kök neden: tarih çıkarımı `now`'u bilmiyor

`m_today` adımı `agreed_date` alanını `type: date` çıkarımla alıyor. Çıkarım modeli göreli tarihleri **gerçek saate** göre çözüyor, vakadaki `now`'a göre değil (vakalarda `now` = 2026-10-14, gerçek tarih 2026-10-10):

- PUB-01 (3/3 aynı): müşteri "bugün ödüyorum" diyor, kayıt `2026-10-10` (gerçek bugün), beklenen `2026-10-14`. Ladder sürümünde tarihi model `create_promise`'a olgulardan yazdığı için bu hata yoktu.
- PUB-12: "yarın" `2026-10-11` (Pazar) olarak çıkarılıyor, beklenen `2026-10-15`. Müşteri her düzeltmede "yarın" diyor, `apply_fix` aynı yanlış tarihi yeniden çıkarıyor, döngü tur sınırına kadar sürüyor, sonunda üç ürüne de `refused` notu düşüyor.

## İkinci neden: `all_yes` tek tarihi bütün ürünlere uyguluyor

- PUB-12: müşteri "kartı yarın öderim, diğerlerini ödemem" diyor. Model `m_today`'de kendi başına kart için pazarlık ediyor, müşteri "evet" deyince adım `accepts` oluyor ve `all_yes` **üç ürünü de** anlaşılmış sayıyor (okuma: kart 510, kredi 1320, araba 140, hepsi 11 Ekim).
- PUB-13 (1 tekrarda): müşteri "ikisini de 30 Ekim'de" diyor. Model yalnızca kredi için 23 Ekim'i öneriyor, müşteri kabul ediyor; `agreed_date` = 23 Ekim olarak iki ürüne de yazılıyor. Kart 30 Ekim'de kalmalıydı.
- PUB-12 tekrar 2: onaydan sonra `m_readback` tts'siz kalıyor, "You are welcome" döngüsü, `close_call` hiç gitmiyor.

## Diğer A hataları

- PUB-04 (1/3, iki tekrarda kaldı): müşteri onay sırasında "robot musun?" diye soruyor, ajan cevaplamadan devam ediyor.
- PUB-06 (2/3, bir tekrarda kaldı): taban tutar iki kez öneriliyor (bilinen ifade sorunu).

## Önerilen düzeltmeler (kit, Emre'nin alanı)

1. Göreli tarihi çıkarıma bırakmamak: müşterinin tarih ifadesini metin olarak çıkar ("tomorrow", "30 October", "this Friday"), `dates.py`'de `now`'a göre çöz. En azından: `today`'den önceki tarih `today`'e, iş günü olmayan tarih bir sonraki iş gününe çekilsin ve bu bir bayrakla okumaya yansısın.
2. `m_today` yalnızca "hepsini bugün öderim" için `accepts` olsun; ürün adı geçen ya da kısmi her cevap `proposes` sayılıp ürün merdivenlerine (`enter_1`) taşınsın. `m_today` prompt'u ürün bazında pazarlık yasağı içersin.
3. `m_fix` döngüsüne sınır (iki düzeltmeden sonra kapanış) ve `apply_fix` değeri değiştirmiyorsa aynı okumayı tekrar etmemek.
4. `m_readback` tts'siz girişte okuma satırını yeniden söylesin.

Bu düzeltmeler gelene kadar tek ürünlü brief'te ladder.py yolu daha iyi (A: 9/10 ve 7/10).

## Düzeltmeden sonra (2026-10-10, 23:00 TSİ)

Latif'in isteğiyle düzeltmeyi biz yaptık (`multi.py`, `dates.py`, `ladder.py`, `freya.py`; dal `claude/cool-cori-xe7git`). Yeni ajanlar: `fix-multi-a` 988d3926, `fix-multi-b` f15bb0cb.

| Sürüm | A (3 tekrar) | B (3 tekrar) | Ne değişti |
|---|---|---|---|
| ilk kit | 7/10 | 1/3 | |
| düzeltme 1 (`dd18bf6`) | 8/10 | 2/3 | tarih metin olarak çıkarılıp kodda `now`'a göre çözülüyor; tek ürünlü cevap "hepsi bugün" adımından ürün merdivenlerine gidiyor; okuma her girişte söyleniyor; düzeltme döngüsü 3'te kesiliyor |
| düzeltme 2 (`443400f`) | takıldı | **3/3** | ilk cevapta ürüne özel tarih/tutar korunuyor; belirsiz zamanda bir kez kesin gün soruluyor, sonra son tarih öneriliyor |
| düzeltme 3 (`8c0c5e6`) | 9/10 | 2/3 | "Monday the 26th" ayın 26'sı; okuma aynı mesajdaki soruyu önce cevaplıyor |
| düzeltme 4 (`2bdeceb`) | **10/10** | **3/3** | cevap türü eşiği 0,3 (PUB-12'de "refuses" 0,56 güvenle atılmış, model kendi teklif uydurmuştu); okuma birebir kopyalanıyor |

Platform notları:
- A simülasyonu iki kez bütün kararlar geldikten sonra bir saat "running" kaldı ve çalışma alanını kilitledi (bir arama "initiating" durumunda kalıyor). `freya.run_simulation` artık son karardan 2 dk sonra simülasyonu iptal edip sonuçları okuyor (`60c2c67`, `POST /api/v2/simulations/{id}/cancel`).
- Son ölçümde A'nın iki koşusu model yavaş olduğu için atıldı (kural gereği). Atılan koşularda bir PUB-03 araması dört `verify` sonrası söz kaydetti; yavaş model altında kimlik kapısı ayrıca incelenmeli.

## Kimlik kapısı (PUB-03), 23:30 TSİ

Atılan bir yavaş koşuda müşteri üçüncü yanlış doğum tarihini bir soruyla birlikte verdi ("Twenty one July nineteen ninety. How much do I owe?"). Model soruyu cevapladı, tarihi `verify_identity`'ye hiç göndermedi; dördüncü cevap doğru çıktı, söz kaydedildi (beklenen: `not_verified`/`failed`). Banka kapısı aşılmadı, ama bankanın saydığı bir yanlış cevap atlandı.

Düzeltme (`front.py`, `dcdef64`): aynı mesajda hem tam cevap hem soru/şikâyet varsa önce cevap kontrol edilir, soru sonuçtan sonra cevaplanır; araç açıklamasında da aynı kural.

Canlı kontrol (`fix-multi-a`, sürüm 5): PUB-03 3 tekrarda 3/3. `asks_back` stilinde A: 7 geçti, 3 "no verdict". Üçünün de konuşması ve banka kayıtları doğru (PUB-04'te ajan robot sorusunu önce cevapladı, sonra okudu); hakem bu üç aramada `error` döndü.
