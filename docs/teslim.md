# Teslim kontrol listesi: Pazar gizli koşu (11 Ekim 2026)

Saatler TSİ. Gizli brief'ler **20:00** (17:00 UTC), teslim **23:00** (20:00 UTC; form, kit e-postasındaki adrese). Kaynak kurallar: `docs/hackathon.md`. Yapı: `docs/interfaces.md`.

## 0. Pazar öğlene kadar (hazırlık)

- [ ] `main` güncel, `python3 tools/preflight.py` temiz (testler, anahtar taraması, git).
- [ ] **Koşacak makine bankaya erişebiliyor.** Bu, çalıştırmadan önce denenir: `curl -s -m 15 -o /dev/null -w "%{http_code}\n" https://freya-bank-mock.freyavoice.workers.dev/` → `000` ise koşma (bazı Türkiye ağlarında `*.workers.dev` kesiliyor; VPN ya da erişimi olan makine). Banka olmadan builder yine çalışır ama kendi testi `TEST_UNAVAILABLE` olur.
- [ ] Makinede: `env.sh` (kendi anahtarlarımız), `pip install claude-agent-sdk`, Claude girişi ya da `ANTHROPIC_API_KEY`.
- [ ] Freya çalışma alanında koşan simülasyon yok (aynı anda tek). Eski slotlar çalışma alanında yer tutuyor (200 sınırı) ama sorun değil; slotlar güncellenir.
- [ ] Pratik koşu (A, B, R, R2) yapıldı; son skor ve süre `docs/` altında. Brief R2: `python3 builder/build.py practice/brief-r2/brief-r2.md --slot ours-r2`.
- [ ] Ortak dal: kim koşuyor, hangi makineden, kim gönderiyor, konuşuldu (aynı anda iki koşu **olmaz**).

## 1. 20:00 → gizli koşu (her brief için, sırayla)

Brief dosyalarını olduğu gibi `briefs/hidden-1.md` ve `briefs/hidden-1.openapi.json` olarak kaydet (ikinci için `hidden-2`). **Elle düzenleme yok.**

```bash
cd build-the-builder && git pull && source env.sh
python3 tools/preflight.py                    # koşmadan önce
python3 builder/build.py briefs/hidden-1.md --tools briefs/hidden-1.openapi.json --slot hidden-1 2>&1 | tee traces/hidden-1.console.txt
```

`--tools` **şart**: yoksa builder kit'in eski `tools/openapi.json`'unu kullanır (gizli API'nin alanları farklı olabilir). Her gizli brief kendi araç API dosyasıyla gelir. Bir brief başka bir dosyanın üstüne kuruluyorsa (halka açık B, A'nın üstüne kuruluydu) dosyalar sırayla verilir: eski önce, değiştiren sonra (`build.py a.md b.md --tools ...`).

- Süre: en fazla 30 dk (`--minutes 30`), pratikte 8-16 dk. Sonra ikinci brief. Her ikisi bittiğinde en az 30 dk marj kalsın.
- Çıktı: `submission/hidden-1.workflow.json`, `traces/hidden-1-<zaman>.{log,jsonl}`, `out/hidden-1/`.
- Sonda "no workflow to submit" yazarsa: konsol çıktısını oku, **brief'e özgü hiçbir şey yazmadan** yalnızca çökme düzeltmesi yap (izin var), bir daha koş (izin var; teslim edilen workflow'un trace'i o koşununki olmalı).
- İkinci brief'in koşusu birincinin simülasyonu bitmeden başlamaz (çalışma alanında tek simülasyon).

## 2. Koşu sonrası, her brief için

- [ ] Konsolda `lint problems` yok; `submitted submission/hidden-N.workflow.json` yazdı.
- [ ] Trace `.log` ilk satırı başlangıç/bitiş, model çağrıları, yaratılan workflow/agent id, test (ya da `TEST_UNAVAILABLE`) içeriyor.
- [ ] Workflow'a Freya'da elle dokunulmadı.

## 3. Teslim (22:00'e kadar bitir, 23:00 son)

```bash
python3 tools/preflight.py hidden-1=hidden-1 hidden-2=hidden-2     # temiz çıkmalı; formu da basar
git add submission traces briefs out && git commit -m "hidden run: submission and traces" && git push
python3 tools/preflight.py hidden-1=hidden-1 hidden-2=hidden-2     # tekrar: HEAD itildi mi
```

- [ ] Form: `team`, `repo`, **itilen commit**, `run_command` = `python3 builder/build.py {brief_path} --tools {tool_api_path}`, `workflows` ve `traces` (preflight basar). Kit e-postasındaki adrese **23:00'den önce** gönder.
- [ ] Repo organizatör için erişilebilir mi (private ise erişim verildi mi)? Soru organizatöre iletildi, yanıt bekleniyordu, **doğrula**.
- [ ] Commit'te gizli brief'ten hiçbir şey **koda, skill'e, kit'e** girmedi (yalnızca `briefs/hidden-*`, `out/`, `submission/`, `traces/` yeni; bu klasörler brief girdisi ve çıktısıdır). `git diff <koşu öncesi commit> HEAD --stat -- builder .claude` boş ya da yalnızca çökme düzeltmesi.
- [ ] Anahtar yok: preflight "no key found".

## 4. Yapma

- Freya'da workflow'u elle düzenleme, `AGENT_LLM`'i değiştirme, başka servis çağırma, platforma yük bindirme.
- Gizli brief'in tatilini, kod adını, tutarını koda ya da prompt'a yazma.
- Aynı anda iki simülasyon/iki koşu başlatma.
- `env.sh`'ı ya da bir anahtarı commit'leme (konsol çıktısında anahtar çıkıyorsa `.txt`'yi de taramadan ekleme).

## 5. Arıza çizelgesi

| Belirti | Ne yap |
|---|---|
| Banka `000` / `Connection reset` | VPN ya da erişimi olan makine; yoksa builder `TEST_UNAVAILABLE` ile bitirir, teslim yine geçerli |
| `Workspace plan limit reached` | yeni slot yaratma; mevcut slotu güncelle (`--slot` aynı kalsın) |
| Freya 5xx | `deploy` zaten 4 kez dener; yine olmazsa 1-2 dk bekle, aynı komutu bir daha koş |
| Kod düğümleri sandbox hatası | workflow'da yeniden deneme var; sorun sürerse koşuyu birkaç dk sonra tekrarla |
| Claude API hatası / ajan çöktü | aynı komutu yeniden koş; trace'te iki koşu varsa form doğru olanı göstersin |
| Süre doldu, workflow yok | konsolu oku, çökme düzeltmesi, yeniden koş (kalan süre izin veriyorsa) |
