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

## Geri alınanlar

(yok)

## Sıradaki adım

Madde 1 için "ajan" = builder'ın güncel kitle kurduğu ajanlar (`e2e-a`, `e2e-b`, `e2e-r`): yarın da builder kuracak, elle yapılmış referanslar değil.
Tek vaka kontrolü (`m2.sh`): A pieces PUB-07 3/3, A pieces PUB-06 3/3 (düzeltmeler tuttu); B talkative PUB-11 0/3 (madde 8'i buldurdu); B in_words PUB-12 simülasyon 502 ile açılmadı.

1. Koşuyor (`m3.sh`, kit `cc` sonrası, ajanlar e2e-a v4, e2e-b v3, e2e-r v2): önce 3 tek vaka kontrolü, sonra tur 2: B ve A normal + 5 stil, R; her biri 3 tekrar. Sonuçlar `results/m3-*.log`, R için `results/m3-r-rescored.log`.
4. R2 yapısal: `e2e-r2` 12/12 tarih ve kapanış kodları; `test_brief_r2` yeşil.
