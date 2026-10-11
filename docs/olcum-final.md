# Son ölçüm ve doğrulama (11 Ekim 2026)

Görev: `/loop` talimatı (Latif). Gizli brief'ler 20:00 TSİ (17:00 UTC). 19:30 TSİ'den (16:30 UTC) sonra yalnız çökme düzeltmesi. Bu dosya her ölçümden ve değişiklikten sonra güncellenir; yeni bir oturum "Sıradaki adım"dan devam eder.

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

## Geri alınanlar

(yok)

## Sıradaki adım

1. Koşuyor (`m4.sh`, ajanlar yeni kitle yeniden üretildi): tek vaka kontrolleri (B pieces PUB-12/13, A corrects PUB-04/06), A talkative/asks_back/in_words, R (+ `rescore_close.py`). `results/m4-*.log`.
2. Sonra tur 3 tam: B normal + 5 stil, A normal + pieces + corrects (2 saatlik sınır yüzünden ayrı iş).
3. R2 yapısal: `e2e-r2` 12/12, `test_brief_r2` yeşil.
