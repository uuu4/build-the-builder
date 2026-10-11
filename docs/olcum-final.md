# Son ölçüm ve doğrulama (11 Ekim 2026)

Görev: `/loop` talimatı (Latif). **Döngü 15:30 TSİ'de (12:30 UTC) biter** (Latif, 11:30'da): son ölçüm, main fast-forward, issue #3 özeti. Gizli brief'ler 20:00 TSİ (17:00 UTC). 19:30 TSİ'den (16:30 UTC) sonra yalnız çökme düzeltmesi. Bu dosya her ölçümden ve değişiklikten sonra güncellenir; yeni bir oturum "Sıradaki adım"dan devam eder.

Saatler TSİ (konteyner UTC, +3). Not: `docs/olcum-multi.md`'deki "23:00 TSİ" gibi saatler aslında UTC'dir.

## Ortam

- Bulut konteyneri, bankaya ve Freya'ya erişiyor. `python3 tools/preflight.py`: ALL CHECKS PASSED (03:00).
- Dal `claude/cool-cori-xe7git`, main (`71f77ee`, skill: her brief için multi.py) birleştirildi.
- Referans ajanlar (kit örnek spec'lerinden, `examples/multi-brief-*`): `fix-multi-a` 988d3926 (A), `fix-multi-b` f15bb0cb (B).

## Yapılanlar

| Saat | Ne | Sonuç |
|---|---|---|
| 02:49 | builder uçtan uca R2 (`e2e-r2`, form komutu, araç API'si konumsal) | 127 sn; 12/12 vakada tarih/sıra/deneme doğru; 14 kapanış kodu doğru |
| 02:49 | builder uçtan uca A (`e2e-a`, agent 79002a49) | 287 sn, kendi testi koştu; **A 3 tekrar: 10/10** |
| 03:00 | builder uçtan uca A+B (`e2e-b`, agent 5069d381) | 313 sn; **B 3 tekrar: 2/3**. PUB-12'nin 3. tekrarı Freya'da hiç başlamadı (0 mesaj, simülasyon takıldı, koruma iptal etti): platform, ajan değil. Tek vaka yeniden koşuluyor |
| 03:11 | builder uçtan uca R (`e2e-r`, agent bcf59d65) | 79 sn; memo kuralları doğru (öncelikli bant 6. iş günü, pencere 17:00, "iki iş günü"); canlı ölçüm stillerden sonra |
| 03:10 | `tools/rescore_close.py` | R gibi kodları pratik bankada olmayan brief'ler için puanı `close_call` argümanlarından hesaplar; A koşusunda 10/10 ile aynı sonucu verdi |

## Sonuçlar

### Tur 1 (04:00, builder ajanları `e2e-a`/`e2e-b`, kit `e560e61`), her biri 3 tekrar

| | normal | pieces | corrects | talkative | asks_back | in_words |
|---|---|---|---|---|---|---|
| A | 10/10 | 7/10 | 6/10 | 5/10 | 10/10 | 9/10 |
| B | 2/3 (PUB-12 platform) | 1/3 | 2/3 | 1/3 | 2/3 | 1/3 |

Kök nedenler (konuşmalar okundu):
1. **Ölçüm hatası:** `freya.run_simulation` koruması takılan simülasyonu aramalar hâlâ sürerken iptal ediyordu; banka kaydı erken okundu ("get_account'tan sonra kapanmadı" hatalarının hepsi). Düzeltildi: bütün aramaların bitmesi beklenir, en çok 10 dk.
2. **Okuma LLM girişi:** model okuma yerine bandın izin vermediği bir teklif uydurdu ve kayıttan önce "recorded" dedi (B PUB-12). Okuma yeniden sabit satır; LLM girişi yalnız uzlaşma mesajında soru varsa (`asked_q`).
3. **Okuma döngüsü:** "No, Monday the twenty sixth" `m_fix`'e gitti, model değişikliği tekrarlayıp onay aldı, `none` sayıldı (A PUB-07). Okuma adımı değişikliği kendisi çıkarıp uyguluyor; tek ürün için ürün numarası gerekmiyor; okuma sayısı sınırlı.
4. **Taban altı tutar:** 637,50 teklifine 637 kaydedildi (A PUB-06), krediye 3 (B PUB-11). Tabanın altı kaydedilmiyor: teklif ya da taban.
5. **Haftalı gün:** "the week after next", sonra "Monday" önümüzdeki Pazartesi okundu. Belirsiz kelimeler saklanıyor, çözücü günü haftasıyla okuyor.
6. **Parçalı kimlik cevabı:** "19 October" + "1983" 13 kez yeniden soruldu, araç hiç çağrılmadı (B pieces). Parçaların birleşik hâli tam cevaptır kuralı.
7. **Destek teklifi tekrarı:** hardship adımı teklifi dört kez yaptı (A talkative PUB-05). Bir kez kuralı.
8. **Sayı değişkeni temizlenmiyordu:** platform float değişkene yazılan `''`yi yok sayıyor; kartın 220'si krediye taşındı (B talkative PUB-11). Sayılar 0 ile temizleniyor (`multi.py`).
9. Simüle müşteri kaynaklı (bizim değil): A talkative PUB-09 cümleler yarıda, anlamsız karakter, telefon hanesi hiç verilmiyor.

### Tur 2 (05:00-06:55 TSİ, kit `0-clearing` sonrası), her biri 3 tekrar; arka plan 2 saat sınırında A talkative'de kesildi

| | normal | pieces | corrects | talkative | asks_back | in_words |
|---|---|---|---|---|---|---|
| A | 10/10 | 9/10 | 8/10 | (kesildi) | - | - |
| B | **3/3** | 2/3 | 2/3 | 0/3 | 2/3 | **3/3** |

Yeni kök nedenler (düzeltildi, `kit: digits joined...`):
10. Parçalı telefon hanesi ters birleştirildi: "forty-four" + "zero one" bankaya 0144 gitti, doğru cevap yanlış sayıldı (B pieces PUB-12).
11. "the 15th, sorry, I mean the 16th" ilk tarihi aldı (A corrects PUB-06): düzeltmeden sonraki tarih kazanır.
12. "the thirtieth" yalnız ürün alanına düştü, ikinci belirsiz cevap sayıldı (B pieces PUB-13): ürün alanındaki tarih de bütün cevap için geçerli.
13. Okumada sorulan "Are you a robot?" cevapsız (A corrects PUB-04): okuma ve düzeltme adımları da soruyu algılıyor.
14. Konuşkan müşteride adımın tur sınırı doldu (B talkative PUB-13): merdiven 12→18, ilk adım 10→16.
Kalan, bizim olmayan: kimlik adımında simüle müşterinin hiç cevap vermediği talkative aramaları (B PUB-11), hakemin kimlik sorusu sayımı (asks_back: "geri soru"dan sonra aynı soruyu tekrar sormak "yeniden sormak" sayılıyor).

### Tur 3, 1. kısım (07:00-07:50 TSİ), her biri 3 tekrar

| | sonuç | kalanlar |
|---|---|---|
| B pieces PUB-12/13 (kontrol) | 2/2 | |
| A corrects PUB-04/06 (kontrol) | 1/2 | PUB-06 taban iki kez |
| A talkative | 6/10 | PUB-05 sempati tekrarı, PUB-07 soru tekrarı, PUB-09/10 simüle müşteri kimlikte cevap vermiyor |
| A asks_back | 9/10 | PUB-06 taban iki kez |
| A in_words | **10/10** | |
| R (rescore) | 7/10 | PUB-04 onayla gelen robot sorusu, PUB-06 taban iki kez, PUB-07 müşteri 10 sn'de kapattı |

Kök nedenler (düzeltildi, `kit: no repeated offer...`):
15. Soru ya da araya giren lafa cevaptan sonra teklif tutar ve tarihiyle tekrar ediliyordu; hakem ikinci teklif sayıyor. Merdiven kuralı: tekrar yok, en fazla "Would that work for you?".
16. Hardship'te her laf arasına sempati cümlesi: tek cümle kuralı, sonra nötr.
17. "Am I talking to a robot? Yes, I..." onayla gelen soru cevapsız kaydedildi: `m_answer` önce cevaplar, sonra kayıt için izin ister.

### Tur 4 (08:00-08:45 TSİ), her biri 3 tekrar

| | normal | pieces | corrects | talkative | asks_back | in_words |
|---|---|---|---|---|---|---|
| B | **3/3** | **3/3** | 2/3 | 1/3 | 2/3 | **3/3** |

Kontroller: A asks_back PUB-06 3/3, R PUB-04 3/3 (15 ve 17 tuttu); A talkative PUB-05 hakem cevabı gelmedi, PUB-07 simüle müşteri kimlikte cevap vermedi.

Kök nedenler (düzeltildi, `multi: a proposal with a day...`):
18. Önerilen gün bir anlaşmadır: "both on the thirtieth of October" "That is fine" ile cevaplandı ama yalnız `accepts` kaydı başlatıyordu; model aynı adımda krediyi konuştu, tur bitti (B talkative PUB-13). `prop_k_step` kod düğümü günü çözer; gün yoksa adıma geri döner.
19. Hakem kimlik sorusunun her tekrarını "yeniden sorma" sayıyor (B asks_back/talkative PUB-12): geri soruya cevaptan sonra soru tekrar edilmez ("Whenever you are ready."); laftan sonra ancak iki mesaj cevapsız kalırsa.
Bizim olmayan: B corrects PUB-12 simüle müşteri "on Friday, sorry, I" diye kesiyor, düzeltme hiç söylenmiyor.

### Tur 5 (08:50-09:50 TSİ), her biri 3 tekrar

| | normal | pieces | corrects | talkative | asks_back | in_words |
|---|---|---|---|---|---|---|
| A | **10/10** | **10/10** | 7/10 | 4/10 | **10/10** | **10/10** |
| R (rescore) | **9/10** | | | | | |

Kontroller: B talkative PUB-13 3/3 (18 tuttu); B asks_back PUB-12 1/3 (hakem hâlâ kimlik sorusu sayımı).

Kök nedenler (düzeltildi, `kit: date/amount extraction thresholds...`):
20. "Monday the twenty-sixth" 0,53 güvenle atıldı (eşik 0,6): tarih ve tutar metin alanlarının eşiği 0,3/0,4 (kod her değeri denetliyor).
21. Simüle müşteri düzeltmesini yarıda kesiyor ("ten, sorry", "Thursday, sorry"): ilk değer alınmıyor, hangisi kastedildiği soruluyor (merdiven, geri arama).
22. "You tell me." karşısında teklif tutar ve tarihle tekrarlandı (R PUB-06): örnek cümleli kural.
Talkative'deki kalanların çoğu simüle müşteriden: kimlik hanelerini hiç vermiyor, cümleler yarıda (A PUB-02, 03, 06, 10).

main `248ea34`'e fast-forward edildi (testler yeşil, preflight temiz, ölçümler önceki main'den iyi).

### Tur 6 (10:00-11:00 TSİ), her biri 3 tekrar (platform yavaş: çok sayıda koşu kural gereği atıldı)

| | normal | pieces | corrects | talkative | asks_back | in_words |
|---|---|---|---|---|---|---|
| B | **3/3** | **3/3** | 1/3 | 0/3 | 2/3 | **3/3** |

Kontroller: A corrects PUB-02/06 3/3, PUB-07 2/3; R PUB-06 3/3 (22 tuttu).

23. **Gerileme, geri alındı:** 21'de tarih alanına eklenen "düzeltme yarıda kaldıysa boş bırak" cümlesi çıkarımı bitmiş düzeltmelerde de boşalttı ("the twenty-fifth, sorry, I mean the twenty-sixth" → boş); boş tarih ikinci belirsiz cevap sayılıp son tarihler kaydedildi (A corrects PUB-07, B PUB-11 atılan koşuda). Cümle çıkarım açıklamalarından çıkarıldı ("düzeltilmiş günü ver"), adım talimatında kaldı.
24. İkinci kez günsüz cevap artık son tarihleri kaydetmiyor, ürün merdivenlerine gidiyor.
25. Geri sorudan sonra kimlik sorusu yine tekrarlandı (ikinci geri soruda): örnek cümle eklendi.
Bizim olmayan: B corrects PUB-11 sandbox `code_exec` hatası (service_error), talkative'de kimlik cevabı vermeyen simüle müşteri.

### Tur 7 (11:15-12:42 TSİ): platform bozuk, sonuçlar değerlendirmeye alınmadı

Kontroller (platform sağlamken): A corrects PUB-07 3/3, B in_words PUB-11 3/3 (madde 23 geri alımı tuttu).
A normal 6/10 ve A corrects 6/10, ama kalanların çoğunda hakem gerekçesi "All criteria met" ya da "no verdict"/"analysis never arrived": hakem servisi bozuk. Ardından `POST /api/v2/simulations` 503 ("API key validation is temporarily unavailable"), `GET` 504 ve 30 sn üstü cevaplar; A pieces/asks_back/in_words/talkative ve R hiç koşmadı.
Gerçek görünen kalanlar: A corrects PUB-06 (simüle müşterinin "Thursday, sorry" kesiği), PUB-09 (restructuring öncesi model bir teklif söyledi), PUB-03 (simüle müşteri kimlikte cevap vermedi).

## Geri alınanlar

- `kit: date/amount extraction thresholds...` içindeki çıkarım açıklaması kuralı ("yarıda kalan düzeltmede boş bırak"): ölçüm kötüleşti, `kit: take the cut-off rule out...` ile kısmen geri alındı (madde 23).

## Sıradaki adım

1. 12:45 TSİ: Freya API 503/504 ve zaman aşımı. 15 dk sonra yeniden yokla; düzelmezse dur, issue #3'te Emre'ye sor.
2. Platform düzelirse: ajanları `front: example line...` (madde 25) ile yeniden üret + deploy; A pieces/asks_back/in_words, R, B asks_back PUB-12 kontrolü.
3. 15:30 TSİ: son durum, main fast-forward (madde 23 geri alımı main'e girmeli: main `248ea34` hâlâ hatalı kuralı içeriyor), issue #3 özeti.
