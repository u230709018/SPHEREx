# Ekip Kurulum ve Çalışma Notu

## 1. Kurulum (her ekip üyesi, ~5 dk)

```bash
git clone https://github.com/u230709051/SPHEREx.git
cd SPHEREx
python3 -m venv .venv          # Python 3.10+ önerilir
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --app-dir backend --port 8000
```

Tarayıcıda **http://localhost:8000** adresini açın. Demo hedefleri (`data/results/`) önbellekten anında yüklenir.

- **Yeni bir koordinat** ilk seferde IRSA'dan canlı çekilir ve 1–4 dk sürer. Sonraki açılışlar anlıktır.
- **Önbelleği ısıtmak için** (5 demo hedefi):

  ```bash
  .venv/bin/python scripts/warm_cache.py 5
  ```

## 2. Dosya haritası: kim nereye bakar

| Rol | Dosyalar |
|---|---|
| **A: Veri/Backend** | `backend/spherex_core.py` (sorgu, kesit, temizleme, birleştirme), `backend/pipeline.py` (iş akışı, önbellek), `backend/main.py` (API) |
| **B: Bilim** | `backend/spherex_core.py` → `photometry_at()` (spektrum/fotometri), `backend/catalogs.py` (Gaia, JPL asteroit, pm taşıma), `backend/targets.json` |
| **C: Görüntüleyici** | `frontend/app.js`: `rebuildDisplay`, `render`, `drawOverlay`, oynatma, klavye, URL |
| **D: Paneller + Tasarım** | `frontend/app.js`: `plotSpectrum`, `plotLightcurve`, rozetler/uyarılar; `frontend/style.css`, `frontend/index.html` |
| **E: Sunum/Teslim** | `README.md` (İngilizce, jüri okuyacak), demo videosu, slaytlar, proje sayfası |

## 3. API (frontend ↔ backend)

| Uç nokta | Ne yapar |
|---|---|
| `GET /api/targets` | Demo hedef listesi |
| `GET /api/resolve?q=` | İsim → konum + öz hareket |
| `POST /api/frames` | `{ra, dec, pmra, pmdec, ref_epoch, fov_arcmin, max_per_cell, budget, name}` → önbellekteyse `{status:"done", result_key}`, değilse `{status:"running", job_id}` |
| `GET /api/jobs/{id}` | İlerleme: `stage`, `done`, `total`, `message`, `status` |
| `GET /api/result/{key}` | `grid` (WCS), `epochs`, `frames` (her epoch × dedektör için base64 float32), `points` (spektrum), `lightcurve`, `stats` |
| `GET /api/spectrum/{key}?ra&dec` | Alandaki herhangi bir noktanın spektrumu ve ışık eğrisi |
| `GET /api/gaia?ra&dec&radius_deg&jyears` | Her epoch'a taşınmış Gaia DR3 kaynakları |
| `GET /api/asteroids?ra&dec&half_width_deg&mjds` | Her epoch'ta bilinen asteroit ve kuyruklu yıldızlar |

## 4. Git çalışma düzeni

- **`main` her zaman çalışır durumda kalmalı**, demo buradan yapılacak.
- Herkes kendi dalında çalışsın: `git checkout -b ozellik-adi` → commit → push → GitHub'da Pull Request → biri bakıp merge eder.
- Aynı dosyada iki kişi çalışacaksa önce konuşun. `frontend/app.js`'te C ve D farklı fonksiyonlara dokunsun.
- **Commit'e girmeyenler:** `data/cache/` (2+ GB FITS), `.venv/`, `scratch/`. `.gitignore` bunları zaten dışarıda tutuyor.
- **`data/results/*.json` demo önbelleğidir.** Pipeline değişip `PIPELINE_VERSION` artarsa eski dosyaları silip `warm_cache.py`'yi yeniden çalıştırın.

## 5. Kurallar (teslim)

- **Kodda, arayüzde, README'de ve sunumda dil İngilizce.** Bu dosya ve `docs/ARASTIRMA_VE_PLAN.md` ekip içi notlardır.
- **Yapay zekâ kullanımı beyan edilmeli** (README'de var). AI yardımıyla yazılan yeni dosyalara da başlık yorumu ekleyin.
- **NASA, JPL, CSA ve ESA logoları kullanılmayacak.**
- **Depo şu an Private.** Teslimden önce **Settings → General → Danger Zone → Change visibility → Public** yapılmalı. Jüri giriş yapmadan erişebilmeli.
- **Son teslim Pazar 23:59.** Hedef Pazar 22:30 (bkz. `docs/ARASTIRMA_VE_PLAN.md` Bölüm 5).

## 6. Açık işler (sıradaki)

- [ ] RW Aur ve R Dra arayüzde test (önbellek hazırlanıyor)
- [ ] Yayına alma (Render / Railway / Hugging Face Spaces). `data/results` repo'da olduğu için demo anında açılır
- [ ] PSF fotometrisi (WISE 0855'in kısa dalga boylarındaki kirlenme)
- [ ] Aladin Lite bağlam paneli + DSS üzerinde 1950→2026 hareket izi
- [ ] "Track a Solar System object" modu (IRSA MOST, demo: 3I/ATLAS) + CADC SSOIS linki
- [ ] Ölçülen öz hareket (PSF centroid) ve Gaia karşılaştırması
- [ ] Mobil görünüm kontrolü, demo videosu (≤30 sn), 7 slayt
