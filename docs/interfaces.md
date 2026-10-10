# Mimari ve arayüzler (v1.0, 2026-10-10 gece)

v0.4.1'in yerine geçer (plan/derleyici mimarisi; `docs/archive/interfaces-v0.4.1.md`). Bu dosya **gerçekte çalışan** yapıyı anlatır. Kit ile çelişirse kit geçerli.

## Katmanlar

```
python3 builder/build.py <brief>... --tools <tool_api.json> --slot <ad> [--minutes 30]
```

1. **`builder/build.py` (O, Latif).** Saati tutar (kapanışa 4 dk ayırır), trace'i açar (`traces/<slot>-<zaman>.{jsonl,log}`), Claude Agent SDK ajanını başlatır, ajan bitince ya da süre dolunca **kendisi** lint + kaydet + dışa aktar (`submission/<slot>.workflow.json`) yapar. Ajan çökse de elde workflow varsa teslim eder.
2. **Ajan (S, Emre).** Model `BUILDER_MODEL` (varsayılan `claude-opus-5-5`), skill `collections-builder` (`.claude/skills/`). Brief'i okur, `out/<slot>/` altına belirtimleri ve `gen.py`'yi yazar, çalıştırır, dağıtır, test eder, düzeltir.
3. **Kod araçları ve kit (K, Emre).** Hata yapılmaması gereken her şey kodda.

## Kod araçları (`python3 -m builder.cli`, ajan Bash ile çağırır)

| Komut | İş |
|---|---|
| `spec-doc` | ön kısım belirtiminin biçimini basar |
| `lint <workflow>` | yerel denetim |
| `deploy <slot> <workflow>` | lint + dryRun + kaydet + yayınla (5xx/ağda 4 deneme), `out/<slot>/deployed.json` |
| `test <slot> [--brief A] [--only ID] [--style S] [--reps N]` | pratik müşteriler; süre yoksa reddeder; banka/platform erişilemezse `TEST_UNAVAILABLE` (çıkış 3) |
| `event <tür> <mesaj>` | trace'e satır |

## Kit (`builder/kit/`), brief'ten bağımsız

| Modül | İş |
|---|---|
| `front.py` | açılış, kim açtı, üçüncü kişi + geri arama, kimlik, insan isteği, ön kapanışlar. Girdi: `front.json` (biçim `cli spec-doc`; eksik parça adıyla bildirilir) |
| `dates.py` | takvim, bantlar, son tarihler, taban, ürün sırası (`order_by`), ürün başına `s<k>_*` değişkenleri ve sabit cümle şablonları. Girdi: `dates.json` |
| `ladder.py` | bir ürün için ikna merdiveni (teklif başına bir düğüm; sayım grafta) |
| `multi.py` | 1-3 ürün: ürün başına merdiven, tarihin ürün son tarihine **kodla** çekilmesi, tek okuma + onay, kayıt aşaması (`create_promise` iki açık deneme, `add_note`), sonucun kodla hesabı. Girdi: `multi.json` |
| `graph.py`, `pycode.py` | düğüm/geçiş yardımcıları; kod düğümü yardımcıları (`isbiz`, `say`, `read_list`, `money`) |
| `openapi.py` | araç API dosyasından işlem/alan/enum; **kimlik alanı, kapatma işlemi, ok bayrağı dosyadan bulunur** |
| `lint.py`, `deploy.py` | yerel denetim; dryRun + kaydet + dışa aktar (yeniden denemeli) |

Referans üreticiler: `examples/multi-brief-a/` (tek ürün, not yok) ve `examples/multi-brief-b/` (çok ürün). Her biri `front.json`, `multi.json`, `dates.json`, `gen.py` (spec'leri yükleyip workflow'u yazar; `SPEC_DIR`, `TOOL_API` ortam değişkenleriyle başka belirtimlere de çalışır).

## Bir slotun dosyaları (`out/<slot>/`)

`rules.md` (kural listesi, çakışmada **belgedeki tarih** kazanır, paketteki sıra değil) · `front.json` · `ladder.json` (tek ürün) ya da `multi.json` + `dates.json` (çok ürün) · `gen.py` · `workflow.json` (**elle düzenlenmez**, `gen.py` yeniden koşturulur) · `deployed.json` · `test-*.json`.

## Kurallar

- **Sızıntı yok:** `builder/` ve skill'lerde pratik/gizli brief değeri (tarih, kod adı, sabit tutar) yok; `builder/tests/test_kit.py::NoLeakTest` denetler. Değerler yalnızca spec dosyalarından gelir.
- **Anahtarlar** yalnızca ortamda (`env.sh`, gitignore'da). `tools/preflight.py` dosyalarda anahtar arar.
- **Araç/alan/kod adları araç API dosyasından**; dosyanın söylemediğini ajan spec'e yazar. Kit sabit isim varsaymaz (`builder/tests/test_alt_api.py`, her adı değiştirilmiş bir bankaya karşı üretir).
- Elle workflow düzenlemesi yok; her değişiklik `gen.py` ya da spec'te, sonra `cli deploy`.
- Belirsiz kuralda Policy açısından güvenli değer; `cli event uncertain_default ...`.

## Dayanıklılık (sırayla)

| Arıza | Davranış |
|---|---|
| Freya 5xx/ağ | `kit/deploy.py` 4 kez dener (8, 16, 24 sn); dışa aktarma olmazsa gönderilen workflow `submission/`'a yazılır |
| Banka/platform test için erişilemez | `cli test` bir kez daha dener, sonra `TEST_UNAVAILABLE`: ajan workflow'u değiştirmeden bitirir |
| Freya kod sandbox'ı çalışmaz | her kod düğümünün bir yeniden deneme ikizi (`<ad>_again`), sonra `close_error`; her düğümün kendi rota değişkeni var (eski değer yanlış yola sokmaz) |
| `create_promise` ilk çağrıda hata | ikinci açık çağrı (`rec2_k`); iki hata → not/`service_error` |
| Ajan çöker, workflow yok | **açık**: `build.py` "no workflow to submit" der. Öneri: süre yarısı dolmadan bir kez yeniden başlat; olmazsa yedek workflow (issue #3) |

## Sahiplik

**S + K:** Emre'nin tarafı (skill'ler, `builder/kit/`, `builder/cli.py`, `examples/`, `practice/brief-r2/`). **O:** Latif'in tarafı (`build.py`, `tools/run_cases.py`, trace, export). Ortak: `cli event`, `docs/`. Kırıcı değişiklikte sürümü artır, issue #3'e not düş.
