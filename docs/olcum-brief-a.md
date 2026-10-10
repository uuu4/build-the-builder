# Ölçüm: örnek skill ile Brief A (kit v3, 2026-10-10)

Builder: `examples/agent_builder.py` + `.claude/skills/build-phone-agent` (değiştirilmeden), model `claude-opus-5-5`.
Ajan: workflow_id `d8045db7-ae61-48c6-9b1e-2cd16f880335`, agent_id `e84ca520-d125-4644-8905-7bbbee1c29ce`.
Çıktılar: `baseline/example-builder/brief-a.workflow.json`, üreteç `baseline/example-builder/gen_brief_a.py`, iz `baseline/example-builder/20261010-123638.jsonl`.

## Builder koşusu

| | |
|---|---|
| Süre | 450 sn, 15 tur, 1,75 USD |
| Kendi testi | 1 koşu, 10 / 10, düzeltme turu yok |

## 3 tekrar (`run_cases.py --brief A --reps 3`)

| Vaka | Koşu 1 | Koşu 2 | Koşu 3 | Sonuç |
|---|---|---|---|---|
| PUB-01 Happy path | PASS | PASS | PASS | 3/3 |
| PUB-02 Third party | PASS | PASS | PASS | 3/3 |
| PUB-03 Identity | PASS | PASS | PASS | 3/3 |
| PUB-04 Dates | PASS | PASS | PASS | 3/3 |
| PUB-05 Hardship | PASS | PASS | PASS | 3/3 |
| PUB-06 Amounts | FAIL | FAIL | PASS | 1/3 |
| PUB-07 Dates | PASS | PASS | PASS | 3/3 |
| PUB-08 Already paid | PASS | PASS | PASS | 3/3 |
| PUB-09 Restructuring | PASS | PASS | PASS | 3/3 |
| PUB-10 Tool failure | FAIL | PASS | PASS | 2/3 |
| Koşu toplamı | 8/10 | 9/10 | 10/10 | **8/10 (3/3 kuralıyla)** |

Koşu süreleri 107, 118, 117 sn. En yavaş ajan turunun medyanı 7, 13, 9 sn (koşu 2'de yavaşlık uyarısı); müşterinin kapattığı başarısız arama yok.

## Başarısızlıklar

**PUB-06 (2 kez).** Banka kaydı iki seferde de doğru (637,50, 16 Ekim). Hakem "minimum bir kez önerilir" kontrolünden düşürdü. Koşu 2 dökümü:
1. Müşteri: tam tutar çok fazla. Ajan: minimum 637,50 **bugün** (kuralın 26 cümlesiyle).
2. Müşteri: bugün olmaz. Ajan: **tam tutar** 2125,10 Cuma 16 Ekim'de (1. ikna denemesi).
3. Müşteri: hâlâ çok. Ajan: minimum 23 Ekim'de (2. deneme, son tarih). Minimum ikinci kez anılıyor.

Brief'in 30. kuralı, müşteri tam tutarın çok olduğunu zaten söylediyse 1. denemenin minimum için olmasını istiyor. Ajan 1. denemede tam tutara geri döndü ve konuşma bir tur uzayınca minimum ikinci kez önerildi. Deneme tutarını "tam tutar çok fazla" bayrağına bağlayan bir kod/rota bunu kapatır.

**PUB-10 (1 kez).** Kayıtlar doğru (ilk `create_promise` hata, ikincisi başarılı, tek söz). Hakem, açılıştaki "this call is recorded" cümlesini sözün kaydedildiği iddiası saydı. Cümle 1. kuralın gereği; büyük olasılıkla hakem gürültüsü. Yine de açılışta "recorded" kelimesinden kaçınan bir ifade ("this call may be monitored and kept on record" gibi) riski düşürebilir; brief'in diline uygunluğu ayrıca tartılmalı.

**Not (aynı gün, sonra):** kendi builder'ımızın ilk çalışması aynı `brief-a` slot'unu kullandı ve bu workflow'un (`d8045db7...`, agent `e84ca520...`) üstüne yazdı (sürüm 3). Yukarıdaki ölçümler sürüm 1'e, yani örnek builder'ın ajanına ait. Örnek builder'ın çıktıları `baseline/example-builder/` altına taşındı; `build.py` artık `ours-<brief>` slot'unu kullanıyor.
