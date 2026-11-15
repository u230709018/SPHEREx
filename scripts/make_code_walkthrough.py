"""
Build the team's Turkish code walkthrough (internal note, like docs/EKIP_KURULUM.md).

Usage: .venv/bin/python scripts/make_code_walkthrough.py [out.html]
       (default output: output/kod_anlatimi.html, a git-ignored folder)
Then open the HTML in a browser and print it to PDF, or:
       msedge --headless --no-pdf-header-footer --print-to-pdf=kod_anlatimi.pdf output/kod_anlatimi.html

The code blocks are cut from the real files by function name, so they always match the
repository. If a function named below is renamed or removed, the script stops with an
error at that line: update the explanation there.

Parts of this file were written with the assistance of an AI coding assistant
(Claude, Anthropic) and reviewed by the team. See README "Use of AI".
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "kod_anlatimi.html"
parts = []


def lines_of(rel):
    return (ROOT / rel).read_text(encoding="utf-8").splitlines()


def block(rel, start, end, head=None):
    ls = lines_of(rel)[start:end]
    while ls and not ls[-1].strip():
        ls.pop()
    cut = head is not None and len(ls) > head
    if cut:
        ls = ls[:head]
    code = html.escape("\n".join(ls))
    more = '<div class="more">… devamı dosyada</div>' if cut else ""
    parts.append(f'<div class="code"><div class="cap">{rel} · satır {start + 1}</div><pre>{code}</pre>{more}</div>')


def PY(rel, name, head=None):
    ls = lines_of(rel)
    i = next(k for k, l in enumerate(ls) if re.match(rf"(def|class) {name}\b", l))
    while i > 0 and ls[i - 1].startswith("@"):
        i -= 1
    j = next((k for k in range(i + 2, len(ls)) if re.match(r"(def |class |@|# ---|[A-Za-z_]+ ?[:=])", ls[k])
              and not ls[k - 1].startswith("@")), len(ls))
    while ls[j - 1].startswith("@"):
        j -= 1
    block(rel, i, j, head)


def JS(rel, name, head=None):
    ls = lines_of(rel)
    i = next(k for k, l in enumerate(ls) if re.match(rf"(async )?function {name}\(", l))
    j = next(k for k in range(i, len(ls)) if ls[k] == "}" or (k == i and ls[k].rstrip().endswith("}")))
    block(rel, i, j + 1, head)


def RNG(rel, start_pat, end_pat, head=None):
    ls = lines_of(rel)
    i = next(k for k, l in enumerate(ls) if re.search(start_pat, l))
    j = next(k for k in range(i, len(ls)) if re.search(end_pat, ls[k]))
    block(rel, i, j + 1, head)


def H1(t): parts.append(f"<h1>{t}</h1>")
def H2(t): parts.append(f"<h2>{t}</h2>")
def H3(t): parts.append(f"<h3>{t}</h3>")
def P(t): parts.append(f"<p>{t}</p>")
def UL(*items): parts.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
def NOTE(t): parts.append(f'<p class="note">{t}</p>')


SC, PL, CT, MV, MN = ("backend/spherex_core.py", "backend/pipeline.py", "backend/catalogs.py",
                      "backend/moving.py", "backend/main.py")
S3, IX, AR = "backend/s3_source.py", "backend/sky_index.py", "backend/archival.py"
AJ, IH, CS = "frontend/app.js", "frontend/index.html", "frontend/style.css"

# ------------------------------------------------------------------ cover
parts.append("""<div class="cover"><div class="kicker">NASA Space Apps 2026 · Planet X and SPHEREx</div>
<div class="title">SPHEREx Time Machine</div><div class="sub">Kodun mantığı: tüm repo, parça parça</div>
<p>Bu belge repodaki her dosyanın ne yaptığını, gerçek kod parçalarını göstererek anlatır.
Kod blokları doğrudan dosyalardan kesilmiştir; başlıklarındaki satır numarası dosyadaki yerini gösterir.</p>
<p>Okuma sırası: önce büyük resim ve kavramlar, sonra sunucu (Python), sonra arayüz (JavaScript),
en sonda aday listesi, gömülü mod ve giriş yardımı gibi paylaşım özellikleri.</p></div>""")

# ------------------------------------------------------------------ 1
H1("1. Büyük resim")
P("Araç, gökyüzünde bir nokta alır ve NASA'nın SPHEREx teleskobunun o noktayı farklı tarihlerde çektiği "
  "görüntüleri art arda oynatır. Sabit yıldızlar yerinde durur; hareket eden ya da parlaklığı değişen bir cisim göze çarpar. "
  "İstenirse aynı alanın 2MASS (~2000) ve WISE (2010) kareleri de araya eklenir; böylece 25 yıllık bir zaman tabanı oluşur.")
P("İki parça vardır. <b>Sunucu</b> (Python, FastAPI) görüntüleri bulur, buluttan keser, temizler, hizalar ve ölçer. "
  "<b>Arayüz</b> (tarayıcıda çalışan JavaScript) hazır kareleri çizer, oynatır ve kullanıcı etkileşimini yönetir.")
H3("Bir isteğin yolculuğu")
UL("Kullanıcı bir isim ya da koordinat yazar. İsimse sunucu onu koordinata ve öz harekete çevirir (<code>/api/resolve</code>).",
   "Arayüz <code>/api/frames</code> adresine istek atar. Sonuç diskte kayıtlıysa hemen döner; değilse arka planda bir iş başlar.",
   "İş: kendi dizinimizde arama (<code>sky_index</code>) → ziyaretlere ayırma → indirilecekleri seçme → AWS'den kesit okuma (<code>s3_source</code>) → temizleme → ortak ızgaraya hizalama → ziyaret ve dedektör başına tek kare → PSF fotometrisiyle tayf ve ışık eğrisi.",
   "İş üç grup halinde ilerler (önizleme, keskinleşme, son) ve her grubun ara sonucu yayınlanır. Arayüz işi saniyede bir yoklar "
   "(<code>/api/jobs</code>), yeni ara sonuç varsa alır (<code>/api/jobs/…/partial</code>) ve hemen oynatmaya başlar.",
   "İş bitince tam sonuç alınır (<code>/api/result</code>); ardından Gaia yıldızları ve 2MASS/WISE kareleri (<code>/api/archival</code>) istenir.")
H3("Dosya haritası")
UL("<code>backend/spherex_core.py</code>: SPHEREx verisiyle ilgili her şey (arama, kesit, okuma, hizalama, fotometri).",
   "<code>backend/sky_index.py</code>: 1,63 milyon SPHEREx görüntüsünün kendi ayak izi dizinimiz; “bu noktayı hangi görüntüler kapsıyor” sorusunu milisaniyede yanıtlar.",
   "<code>backend/s3_source.py</code>: görüntülerin AWS'deki herkese açık kopyasından yalnızca gereken baytları okuyarak kesit üretir.",
   "<code>backend/pipeline.py</code>: uçtan uca iş akışı, aşamalı yayın ve sonuç önbelleği.",
   "<code>backend/archival.py</code>: 2MASS ve WISE kareleri.",
   "<code>backend/catalogs.py</code>: isim çözümleme, öz hareket, Gaia yıldızları, bilinen asteroitler.",
   "<code>backend/moving.py</code>: Güneş Sistemi cismi modu (asteroit ve kuyruklu yıldız takibi).",
   "<code>backend/main.py</code>: web sunucusu ve API adresleri.",
   "<code>frontend/index.html</code>, <code>style.css</code>, <code>app.js</code>: sayfa iskeleti, görünüm, tüm arayüz mantığı.",
   "<code>scripts/build_index.py</code>, <code>data/index/</code>: dizini kuran betik ve dizinin kendisi.",
   "<code>backend/targets.json</code>, <code>scripts/warm_cache.py</code>, <code>data/results/</code>: hazır hedefler ve önceden hesaplanmış sonuçlar.",
   "<code>render.yaml</code>, <code>Dockerfile</code>, <code>requirements.txt</code>: yayınlama ve kurulum.")

# ------------------------------------------------------------------ 2
H1("2. Bilmeniz gereken kavramlar")
UL("<b>RA / Dec (sağ açıklık / dik açıklık):</b> gökyüzündeki enlem-boylam. RA 0–360°, Dec −90° ile +90° arası.",
   "<b>FITS:</b> astronomi görüntü dosyası biçimi. Bir dosyada birden çok bölüm (IMAGE, FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE) bulunur; her bölümün bir başlığı vardır. Başlık 2880 baytlık bloklardan oluşur.",
   "<b>WCS:</b> başlıktaki, gökyüzü koordinatını piksele (ve tersine) çeviren dönüşüm. <b>TAN</b> (gnomonik) izdüşüm, küreyi bir noktada teğet düzleme yansıtır.",
   "<b>MJD:</b> gün sayacı olarak tarih (Modified Julian Date). <b>jyear:</b> ondalıklı yıl (2025.9 gibi).",
   "<b>Dedektör (D1–D6):</b> SPHEREx'in altı dedektörü; her biri 0,75–5,0 µm aralığının bir dilimini görür. D1+D4, D2+D5, D3+D6 ikilileri aynı gökyüzünü görür.",
   "<b>Her pikselin kendi dalga boyu:</b> dedektörlerin önünde konuma göre değişen bir filtre var. Aynı cisim her pozlamada dedektörün başka yerine düşer, yani başka dalga boyunda ölçülür. Tayf böyle oluşur.",
   "<b>Ziyaret (epoch):</b> SPHEREx aynı bölgeye yaklaşık altı ayda bir döner ve birkaç gün içinde çok sayıda görüntü alır. Bu görüntü kümesine ziyaret diyoruz.",
   "<b>Öz hareket (proper motion):</b> bir cismin gökyüzünde yıllık kayması; birimi mili-yay saniyesi/yıl (mas/yr).",
   "<b>Zodi:</b> Güneş Sistemi'ndeki tozun yaydığı arka plan ışığı; görüntüden çıkarılır.",
   "<b>Bayraklar (flags):</b> her piksel için sorun işaretleri (kozmik ışın, doygunluk, hayalet yansıma…).",
   "<b>PSF / ePSF:</b> nokta kaynağın görüntüdeki ışık dağılımı. SPHEREx her görüntüde dedektörün bölgelerine göre bir “etkin PSF” tablosu verir.",
   "<b>Kesit (cutout):</b> büyük görüntüden hedefin etrafındaki küçük kare. <b>HTTP Range:</b> bir dosyanın yalnızca belirli bayt aralığını isteme.",
   "<b>Yeniden izdüşüm (reproject):</b> farklı açılarla çekilmiş görüntüleri aynı piksel ızgarasına oturtma.",
   "<b>Birleştirme (co-add):</b> aynı bölgenin birkaç görüntüsünü tek, daha temiz bir karede toplama.")

# ------------------------------------------------------------------ 3
H1("3. backend/spherex_core.py: verinin çekirdeği")
H2("3.1 Sabitler ve bayrak kümeleri")
RNG(SC, r"^IRSA_BASE", r"^MAX_TRANSIENT_PIXELS")
UL("<code>MJYSR_TO_MJY_PER_PIX</code>: görüntüdeki birim (MJy/sr, yüzey parlaklığı) ile bir pikselin kapladığı açıyı çarparak piksel başına akıya (mJy) çevirir.",
   "<code>BAD_FLAGS</code>: ölçüm (fotometri) için kullanılamaz sayılan pikseller.",
   "<code>DISPLAY_BAD_FLAGS</code>: yalnızca kalıcı bozuk pikseller. Görüntülemede daha az piksel maskelenir, çünkü geçici sorunları birleştirmedeki medyan zaten temizler.",
   "<code>ARTIFACT_FLAGS</code>: hareketli cisim gibi görünebilecek sorunlar; kullanıcıya uyarı olarak gösterilir. <code>SATURATION_FLAGS</code>: doymuş piksel.")
H2("3.2 Veri yapıları")
PY(SC, "ImageRecord")
P("Arşivdeki tek bir görüntünün kimliği: dosya yolu, tarih, dedektör ve hangi ziyarete ait olduğu.")
PY(SC, "Cutout", head=30)
P("İndirilmiş bir kesitin tüm içeriği. <code>image</code> sıkı maskelidir (ölçüm için), <code>display</code> hafif maskelidir (görüntüleme için). "
  "<code>epsf</code>, kesitin altındaki dedektör bölgesinin PSF'idir; <code>psf_image</code> bu PSF'i istenen piksel konumuna kaydırıp toplamı 1 olan bir model görüntü üretir. "
  "<code>wavelength_at</code> bir pikselin dalga boyunu, <code>flag_names_at</code> bayrak bitlerinin adlarını verir.")
H2("3.3 Görüntüleri bulma: önce kendi dizinimiz, sonra IRSA")
PY(SC, "find_images")
PY(SC, "find_images_tap")
P("Dizin dosyası kuruluysa (<code>data/index/</code>) arama tamamen yereldir ve ağa hiç çıkmaz; IRSA'nın veritabanı kapalıyken de çalışır. "
  "Dizin yoksa eski yol, IRSA TAP'a giden tek ADQL sorgusu kullanılır; o da 3 kez, artan beklemeyle denenir.")
H2("3.4 Ziyaretlere ayırma ve indirme bütçesi")
PY(SC, "group_epochs")
P("Görüntüler zamana göre sıralanır. Bir öncekinden 10 günden fazla ara varsa ya da ziyaret 40 günü aşacaksa yeni ziyaret başlar. "
  "İkinci kural, sürekli gözlenen derin alanların tek dev ziyaret olmasını önler.")
PY(SC, "budget_select")
P("Her (ziyaret, dedektör) hücresinden en fazla N görüntü seçilir; fazlası varsa zamana eşit aralıklarla yayılmış olanlar alınır.")
H2("3.5 Kesit indirme: önce AWS, sonra IRSA")
PY(SC, "cutout_url")
PY(SC, "_parse_spherex_cutout")
PY(SC, "fetch_cutout")
P("Her kesit, IRSA adresinin özetiyle (SHA-1) adlandırılıp diske yazılır; aynı kesit ikinci kez indirilmez. "
  "SPHEREx kesitlerinde adres çözülür ve önce AWS'deki kopyadan okunur (Bölüm 5). Bu başarısız olursa IRSA'nın kesit servisi 2 kez denenir; "
  "400/404/500 yanıtı “kesit bu görüntüyle örtüşmüyor” demektir. Aynı fonksiyon 2MASS/WISE kesitleri için de kullanılır.")
PY(SC, "fetch_all")
H2("3.6 Kesiti okuma ve temizleme")
PY(SC, "load_cutout", head=40)
UL("Görüntüden zodi modeli çıkarılır (<code>IMAGE − ZODI</code>).",
   "FLAGS bölümünün başlığındaki <code>MSKN*</code> anahtarları, bayrak adı ile bit numarasını eşler; <code>mask_of</code> istenen adlardan bir bit maskesi kurar.",
   "EPSF tablosundan kesit merkezine en yakın bölgenin PSF'i seçilir (fotometri için).",
   "İki kopya üretilir: hafif maskeli <code>display</code> ve sıkı maskeli <code>image</code>. Maskelenen pikseller NaN yapılır.",
   "<code>n_transient</code>: karedeki geçici olay sayısı; çok yüksekse kare atılır.")
H2("3.7 Ortak ızgara ve kare üretimi")
PY(SC, "make_grid")
P("Hedefi merkez alan, kuzeyi yukarıda olan bir ızgara. Piksel sayısı tek sayıya yuvarlanır ki hedef tam orta piksele düşsün. "
  "<code>cdelt</code>'in ilk değeri eksidir: sağa gidildikçe RA azalır, yani doğu solda kalır.")
PY(SC, "reproject_one")
PY(SC, "combine_cell")
P("Her kesit tek başına ızgaraya taşınır (<code>reproject_one</code>) ve ağırlığıyla saklanır; böylece aşamalı yüklemede her görüntü yalnızca bir kez işlenir. "
  "<code>combine_cell</code> bir (ziyaret, dedektör) hücresini birleştirir: 3 ya da daha fazla görüntüde piksel medyanı (kozmik ışınlar elenir), "
  "daha azında 1/varyans ağırlıklı ortalama.")
H2("3.8 Fotometri: PSF fiti ve Gaia komşularından ayrıştırma")
PY(SC, "_psf_fit")
UL("Model: hedefin PSF'i + yakındaki (1–5,5 piksel) en fazla 6 Gaia yıldızının PSF'i + sabit bir arka plan.",
   "Bu sütunlar bir doğrusal denklem sistemine dizilir ve varyans haritasıyla ağırlıklandırılmış en küçük kareler ile çözülür. Çözümün ilk elemanı hedefin akısıdır.",
   "Belirsizlik kovaryans matrisinin ilk köşegen elemanından gelir. 1 pikselden yakın komşu ayrılamaz, o yüzden alınmaz.")
PY(SC, "photometry_at", head=24)
UL("Önce eski yöntemle açıklık (r = 2 piksel) ve halka arka planı hesaplanır; PSF fiti olmazsa bu değer kullanılır.",
   "<code>method=\"psf\"</code> ve yıldız doymamışsa <code>_psf_fit</code> çağrılır; sonuçta kaç komşunun ayrıldığı (<code>n_blend</code>) da döner.",
   "<b>Doymuş yıldızlar:</b> merkez dolmuşsa ölçüm doymamış kanatlardan (1,5–5 piksel) yapılır: mutlak akı değil, güvenilir göreli ışık eğrisi.",
   "Her ölçüm o pikselin dalga boyuyla birlikte döner; tayfın bir noktası böyle oluşur.")
NOTE("Sonuç: WISE 0855, 8″ ötesindeki G = 16 yıldızdan ayrıştırılınca kısa dalga boylarında karanlık çıkar; uzun dalga boyları WISE W2 ve Spitzer ile uyuşur.")

# ------------------------------------------------------------------ 4
H1("4. backend/sky_index.py: kendi görüntü dizinimiz")
P("<code>scripts/build_index.py</code>, AWS'deki her SPHEREx dosyasının yalnızca başlığını (~9 kB / 65 MB) okuyup her pozlama için bir kayıt tutar: "
  "referans dedektörün merkezi (birim vektör x, y, z), TAN dönüşümü, MJD ve dosya adı parçaları. D1–D3 yan yana, D4–D6 onların ikizi olduğundan "
  "diğer dedektörlerin ayak izi sabit odak düzlemi haritalarıyla (<code>focal_plane.json</code>) türetilir.")
RNG(IX, r"^IDX_DIR", r"^GROUP_DETS")
PY(IX, "find")
UL("<b>1. adım:</b> hedefin birim vektörü ile her pozlamanın merkez vektörünün nokta çarpımı, aralarındaki açının kosinüsüdür. 6,6°'den yakın olanlar aday kalır. 3 boyutlu bir arama tek sayı karşılaştırmasına iner.",
   "<b>2. adım:</b> adaylar için hedefin piksel konumu tek seferde (vektörel) hesaplanır (<code>_tan_pix</code>).",
   "<b>3. adım:</b> odak düzlemi haritası bu konumu her dedektör ikilisine taşır; 2040 × 2040 piksel alanın (20 piksel pay ile) içine düşenler tutulur.",
   "Sonuç: (S3 anahtarı, MJD, dedektör) listesi; birkaç milisaniye.")
H2("4.1 Yeni veri sürümü gelince dizini güncellemek")
PY("scripts/list_s3.py", "rank")
PY("scripts/list_s3.py", "week_folders")
P("<code>list_s3.py</code> sürüm klasörlerini (dr1, qr2, qr3…) kovanın kendisinden okur; hiçbir sürüm adı kodda yazılı değildir. "
  "Aynı hafta birden çok sürümde varsa en iyisi seçilir: Data Release, Quick Release'i yener; aynı türde büyük numara küçüğü yener. "
  "Bugün bu kural dr1 (2025 W17 – 2026 W20) ve qr3'ü (2026 W20 – W40) seçer; qr2'nin haftaları bu ikisinde yeniden işlenmiştir. "
  "NASA qr4 ya da dr2 yayımlayınca betik onları kendiliğinden alır.")
RNG("scripts/build_index.py", r"Exposures already in the existing index", r"done = set\(known\)")
P("<code>build_index.py</code> var olan dizindeki pozlamaların yönelimini dizinden geri kurar ve bunları yeniden okumaz; yalnızca listede yeni olan "
  "pozlamaların başlıkları AWS'den okunur. Yeni klonlanmış bir repoda bile güncelleme saatler değil dakikalar sürer. Paketleme sırasında eski ve yeni kayıtlar birleşir.")

# ------------------------------------------------------------------ 5
H1("5. backend/s3_source.py: buluttan doğrudan kesit")
P("SPHEREx Level-2 görüntüleri sıkıştırılmamış FITS dosyalarıdır. Bir satırın dosyadaki yeri başlıktan hesaplanabildiği için, "
  "65 MB'lık dosyanın tamamı yerine yalnızca gereken satırlar HTTP Range ile istenir.")
PY(S3, "_get")
PY(S3, "_header")
P("<code>_get</code> belirli bir bayt aralığını ister, geçici hatalarda 4 kez dener; 403/404 “dosya yok” sayılır. "
  "<code>_header</code>, 80 baytlık kartlar arasında <code>END</code> kartını bulana kadar okur ve verinin başladığı baytı döndürür.")
PY(S3, "_rows")
PY(S3, "_compressed_rows", head=12)
P("IMAGE, VARIANCE ve ZODI'de istenen satırlar doğrudan okunur. FLAGS bölümü satır satır RICE ile sıkıştırılmıştır: önce o satırların tanımlayıcıları, "
  "sonra yalnızca ilgili sıkıştırılmış veri okunup çözülür.")
PY(S3, "cutout", head=34)
UL("Görüntünün piksel alanında hedefin konumu WCS ile bulunur; merkez görüntünün dışındaysa <code>None</code> (IRSA'nın kuralıyla aynı).",
   "Kesit kutusunun satırları her bölümden okunur, başlıklardaki referans pikseli (<code>CRPIX</code>) kutuya göre kaydırılır (<code>_shift</code>).",
   "EPSF tablosundan yalnızca kesit merkezinin altındaki bölge okunur; dalga boyu tablosu (WCS-WAVE) da eklenir.",
   "Sonuç, IRSA kesitiyle aynı düzende bir FITS dosyasıdır; boru hattının geri kalanı farkı bilmez.")

# ------------------------------------------------------------------ 6
H1("6. backend/pipeline.py: iş akışı ve önbellek")
PY(PL, "job_key")
PY(PL, "cached_result")
P("Her isteğin parametreleri bir anahtara çevrilir. Tarih aralığı verilmemişse anahtara hiç girmez; böylece eski kayıtlı sonuçlar geçerli kalır. "
  "Sonuç <code>data/results/&lt;anahtar&gt;.json</code> dosyasına yazılır. <code>PIPELINE_VERSION</code> artırılırsa eski sonuçlar yok sayılır.")
PY(PL, "cutouts_for")
P("Tıklanan bir noktanın tayfını ölçmek için ham kesitler gerekir. Son 4 alanın kesitleri bellekte tutulur; yoksa diskteki önbellekten yeniden okunur.")
PY(PL, "gaia_neighbors")
P("Alandaki Gaia yıldızları her ziyaretin tarihine taşınır. PSF fitinde hedefin 6–36″ yakınındaki yıldızlar komşu olarak modele eklenir (<code>measure_points</code>).")
PY(PL, "measure_points")
PY(PL, "light_curve")
P("Işık eğrisi: her (ziyaret, dedektör) için iyi noktaların medyanı; belirsizlik medyanın standart hatası (1,253 × sapma / √n).")
PY(PL, "run_frames_job", head=60)
UL("Alan, hedefin 2025.9'daki konumuna ortalanır; hızlı cisimler katalogdaki eski konumlarında aranmaz.",
   "İsteğe bağlı tarih aralığı, indirmeden önce görüntü listesine uygulanır. Aralıkta görüntü yoksa hata mesajı o konumun gözlendiği tarihleri sayar.",
   "Görüntüler üç gruba ayrılır: <b>preview</b> (ekrandaki dedektörlerin her ziyaretinden 1 görüntü), <b>sharper</b> (aynı dedektörlerin kalanı), <b>final</b> (diğer dedektörler).",
   "Önizleme tek başına indirilir; ekrana gelir gelmez diğer gruplar sırayla kuyruğa girer, böylece indirme ve işleme üst üste biner.",
   "Her görüntü bir kez ızgaraya taşınır, bir kez ölçülür. Sonraki gruplarda kareler ve tayf 4 saniyede bir yeniden yayınlanır (<code>snapshot</code> → <code>publish</code>); tayf ve ışık eğrisi canlı dolar.",
   "Gaia komşuları yan iş parçacığında, ilk görüntü gelmeden çekilmeye başlar; hazır olmadan ölçüm bekletilir, en sonda zorunlu yapılır.")

# ------------------------------------------------------------------ 7
H1("7. backend/archival.py: 2MASS ve WISE kareleri")
RNG(AR, r"^SURVEYS = \[", r"^\]")
PY(AR, "_frame")
PY(AR, "archival_frames", head=30)
UL("IRSA'nın SIA servisi alanı kapsayan 2MASS ve AllWISE görüntülerini listeler (TAP kapalıyken de çalışır).",
   "Her bant, dalga boyu yakın olan SPHEREx dedektörüne eşlenir: J→D2, Ks→D3, W1→D4, W2→D6.",
   "Görüntüler SPHEREx çözünürlüğüne yaklaşmak için Gauss ile yumuşatılır ve aynı ızgaraya taşınır. Ziyaret numarası eksi sayıdır (2MASS −2, WISE −1).",
   "Sonuç <code>arch_&lt;anahtar&gt;.json</code> olarak saklanır; IRSA'ya ulaşılamadıysa saklanmaz ki sonra yeniden denensin.")

# ------------------------------------------------------------------ 8
H1("8. backend/catalogs.py: isimler, öz hareket, Gaia, asteroitler")
PY(CT, "propagate")
P("Bir konumu öz hareketiyle başka bir yıla taşır. 3,6 milyon, mili-yay saniyesini dereceye çevirir; RA'da <code>cos(dec)</code>'e bölünür.")
PY(CT, "resolve")
P("İsim çözümleme üç basamaklıdır: yerleşik hedefler (<code>targets.json</code>), SIMBAD'ın Harvard kopyası, CDS Sesame. "
  "Hiçbir servis yanıt vermezse <code>ResolverDown</code> atılır; servis yanıt verdi ama isim yoksa <code>None</code> döner (bkz. Bölüm 11.2).")
PY(CT, "gaia_sources")
P("Gaia DR3 yıldızları önce ESA arşivinden, olmazsa MAST'tan çekilir ve 2016.0'dan her ziyaretin tarihine taşınır.")
PY(CT, "known_small_bodies", head=14)
P("JPL'in servisi verilen tarihte alandaki bilinen asteroit ve kuyruklu yıldızları döndürür.")

# ------------------------------------------------------------------ 9
H1("9. backend/moving.py ve backend/main.py")
H2("9.1 Güneş Sistemi cismi modu")
P("Asteroitler ve kuyruklu yıldızlar hızlı hareket eder. Bu modda her kare cismin o anki konumuna ortalanır; cisim ortada durur, yıldızlar akar.")
PY(MV, "most_query", head=22)
P("IRSA'nın MOST aracı cismin yörüngesini hesaplar ve onu içeren SPHEREx görüntülerini listeler. İsim birden çok cisimle eşleşirse "
  "<code>AmbiguousName</code> atılır ve arayüz “Did you mean” seçenekleri gösterir.")
H2("9.2 Web sunucusu")
RNG(MN, r"^class FramesRequest", r"date_end: str")
P("<code>FramesRequest</code>, gelen isteğin biçimini ve sınırlarını tanımlar; tarih alanları YYYY-AA-GG biçiminde olmalıdır.")
PY(MN, "_run")
P("İş, bir iş parçacığı havuzunda çalışır. <code>publish</code>, ara sonucu iş kaydına yazar ve sayacını (<code>partial_n</code>) artırır.")
PY(MN, "frames")
P("Kayıtlı bir sonuç aranırken üç seçenek denenir: tarihsiz tam sonuç (sayfa tarihleri kendisi süzer), tam kalitede aynı aralık, birebir aynı istek. "
  "Biri varsa “done” döner; yoksa iş başlatılır ve iş numarası döner.")
PY(MN, "job_partial")
PY(MN, "spectrum")
P("Kalan adresler ince sarmalayıcılardır: <code>/api/targets</code>, <code>/api/resolve</code>, <code>/api/moving</code>, <code>/api/jobs</code>, "
  "<code>/api/result</code>, <code>/api/index</code>, <code>/api/archival</code>, <code>/api/gaia</code>, <code>/api/asteroids</code>. "
  "Statik dosyalar <code>no-cache</code> ile sunulur ki yeni yayın hemen görünsün.")

# ------------------------------------------------------------------ 10
H1("10. Arayüz: index.html, style.css, app.js")
P("<code>index.html</code> iskelettir: üstte arama çubuğu, tarih kutuları ve hazır hedefler; ortada iki üst üste tuval "
  "(<code>#img</code> görüntü, <code>#overlay</code> işaretler), altında kontroller ve paylaşım düğmeleri; yanda tayf, ışık eğrisi, aday listesi ve notlar. "
  "Grafikleri Plotly, gökyüzü bağlam haritasını Aladin Lite çizer. Tüm mantık <code>app.js</code>'tedir.")
P("<code>app.js</code> bir öğeyi gizlemek için <code>hidden</code> özniteliğini kullanır. Tarayıcının bu öznitelik için verdiği "
  "<code>display: none</code>, sayfanın kendi CSS kurallarından zayıftır: <code>.group { display: flex }</code> gibi bir kural onu ezer "
  "ve öğe görünür kalır (Track kaydırıcıları bu yüzden her modda görünüyordu). <code>style.css</code>'in başındaki "
  "<code>[hidden] { display: none !important; }</code> satırı gizlemenin her zaman kazanmasını sağlar.")
H2("10.1 Durum nesnesi")
RNG(AJ, r"^const S = \{", r"^\};")
P("Arayüzün hatırladığı her şey tek nesnededir. Çalışırken eklenenler: <code>sph</code> (SPHEREx ziyaretleri), <code>arch</code> (arşiv kareleri), "
  "<code>sphIdx</code>, <code>cands</code> (otomatik adaylar).")
H2("10.2 Girdi ve sunucu çağrıları")
JS(AJ, "parseCoords")
P("Metin iki sayıysa derece olarak alınır. Değilse saat:dakika:saniye ve derece:dakika:saniye denenir; RA 15 ile çarpılır. "
  "Dakika ya da saniye 60 veya üstüyse NaN döner (Bölüm 11.1). Hiçbiri uymazsa <code>null</code> döner ve metin isim sayılır.")
JS(AJ, "api")
JS(AJ, "decodeF32")
H2("10.3 Koordinat dönüşümü")
JS(AJ, "world2pix")
P("Sunucudaki ızgaranın aynısı tarayıcıda hesaplanır; Gaia yıldızları, hedef izi ve kayıtlı adaylar doğru piksele çizilir, tıklama da koordinata çevrilir.")
H2("10.4 Kareleri hazırlama")
JS(AJ, "normaliseFrames")
P("Her kareden medyan çıkarılır ve kare kendi gürültüsüne (MAD × 1,4826) bölünür. SPHEREx ve arşiv kareleri böylece aynı “gürültünün kaç katı” birimine gelir.")
JS(AJ, "composite")
P("Seçili dedektörler toplanıp katkı sayısının kareköküne bölünür. Arşiv karesinde seçili dedektörlerin hiçbiri yoksa en yakın bandı gösterilir.")
H2("10.5 Tarih aralığı")
JS(AJ, "inRange")
JS(AJ, "onRangeChange")
P("Yüklü bir alanda tarih değişince arşive gidilmez: ziyaretler tarayıcıda süzülür; kareler, adaylar, ölçülen hareket, tayf ve ışık eğrisi yeniden çizilir. "
  "Alan daha dar bir aralıkla yüklenmişse ve aralık genişletildiyse yeniden yüklenir. Aralık 2010'a ya da 2000'e uzanırsa WISE ve 2MASS kareleri dahil olur.")
JS(AJ, "rebuildDisplay", head=32)
UL("<b>Blink:</b> her ziyaretin birleşik karesi; arşiv kareleri (işaretliyse) başa eklenir.",
   "<b>Difference:</b> her kare eksi SPHEREx ziyaretlerinin medyanı (şablona hiçbir zaman başka teleskop karışmaz).",
   "<b>Colour</b>, <b>D6−D4</b>, <b>Stack</b>: üç kanal; metan bandı farkı; tüm SPHEREx ziyaretlerinin medyanı.")
H2("10.6 Otomatik aday kutuları")
JS(AJ, "findCandidates", head=40)
UL("Her SPHEREx ziyareti için fark karesi (ziyaret − diğerlerinin medyanı) ve onun sağlam gürültüsü hesaplanır.",
   "Aday: 5σ üstünde, 5×5 komşulukta en yüksek, komşu pikseli de belirgin (kozmik ışın değil), sabit yıldızın küçük kalıntısı değil, çok parlak bir yıldızın kanadında değil.",
   "Türü: yanında belirgin negatif çukur varsa <i>mover?</i> (dipol), başka ziyaretlerde de değişiyorsa <i>variable?</i>, değilse <i>one visit only</i>.",
   "Görüntü sayısı 3'ten az olan ziyaretler (kozmik ışın elenmemiş) ve önizleme atlanır; ~3 Jy'den parlak doymuş hedeflerde arama tümden kapanır.")
H2("10.7 Çizim")
JS(AJ, "computeLimits")
JS(AJ, "stretch")
JS(AJ, "render", head=34)
P("Gizli küçük bir tuvale piksel piksel yazılır (y ekseni ters çevrilir), sonra yakınlaştırmaya göre büyük tuvale kopyalanır.")
JS(AJ, "drawOverlay", head=26)
P("İşaret katmanı: ilk kareyi belirten kesikli çerçeve, otomatik aday kutuları, Gaia yıldızları, asteroitler, hedef izi, kayıtlı adaylar (sarı ★ kare) ve tıklanan nokta.")
H2("10.8 Aşamalı yükleme")
JS(AJ, "loadTarget")
JS(AJ, "runJob", head=36)
P("İş sürerken her saniye durum sorulur; <code>partial_n</code> artmışsa ara sonuç alınır ve <code>onResult(…, {partial: true})</code> ile gösterilir. "
  "<code>token</code>, kullanıcı bu sırada başka hedef yüklerse eski işin ekrana yazılmasını engeller. Hata olursa ekranda kare varsa onlar korunur.")
JS(AJ, "onResult", head=30)
P("Aynı alanın sonraki güncellemeleri gösterilen ziyareti ve oynatma durumunu korur. Kullanıcı yükleme sırasında başka bir noktaya tıkladıysa onun tayfı silinmez.")
H2("10.9 Öz hareketi ölçme")
JS(AJ, "measureMotion", head=32)
P("Her karede hedefin tahmini konumu etrafındaki en parlak piksel bulunur ve ağırlık merkezi alınır; zamana karşı doğru uydurulur, eğim yıllık harekettir. "
  "Arşiv kareleri zaman tabanını 25 yıla çıkarır: WISE 0855 için 8,20 ± 0,03″/yıl (katalog 8,15). Kare başına 0,12 piksel sistematik hata tabanı eklenir.")
H2("10.10 Işık eğrisi")
JS(AJ, "plotLightcurve", head=16)
P("Kaynak tespit edilen dedektörlerde akı medyana bölünür; hiçbir dedektörde kaynak yoksa ham mJy değerleri sıfır çizgisi etrafında gösterilir ve bir yıldıza tıklama önerilir.")
H2("10.11 Adres çubuğunda durum")
JS(AJ, "setHash")
JS(AJ, "initFromHash")
P("Her ayar adresin <code>#</code> sonrasına yazılır (tarih aralığı ve <code>embed</code> dahil); adresi açan kişi aynı görünümü görür.")

# ------------------------------------------------------------------ 11
H1("11. Paylaşım ve kullanım kolaylıkları")
H2("11.1 Hatalı giriş uyarısı ve biçim rehberi")
JS(AJ, "inputHelp")
JS(AJ, "submitQuery")
UL("Dakika/saniye 60'ı aşıyorsa ya da RA/Dec gökyüzü dışındaysa ayrı ayrı mesaj verilir.",
   "Metinde hiç harf yoksa (örneğin tek bir sayı) “eksik konum” denir; isim servisine boşuna gidilmez.",
   "İsim bulunamazsa ya da servisler kapalıysa sunucunun mesajı gösterilir.",
   "Her durumda kabul edilen biçimler tıklanabilir örneklerle listelenir. <code>esc</code>, kullanıcı metninin sayfaya HTML olarak karışmasını engeller.")
H2("11.2 İsim çözümlemede yedek servis")
PY(CT, "_simbad_harvard")
P("CDS'in Strazburg'daki sunucuları kapalıyken eski kod her ismi “bulunamadı” diye reddediyordu. Harvard'daki SIMBAD kopyasına küçük bir betik gönderilir; "
  "yanıt <code>RA Dec|pmRA pmDec</code> biçiminde tek satırdır. İsim tek satıra indirilir ki betiğe başka komut karışmasın.")
RNG(MN, r"^@app.get\(\"/api/resolve\"\)", r"^    return r")
P("“Servis kapalı” 503, “isim yok” 404 olarak döner; kullanıcı hangisi olduğunu bilir.")
H2("11.3 Aday listesi")
JS(AJ, "gaiaNear")
P("Gaia yıldızının ekrandaki karenin tarihindeki konumu takımın <code>gaiaPos</code> fonksiyonuyla bulunur; böylece 2MASS/WISE karesindeyken de doğru yere bakılır.")
JS(AJ, "addSaved")
JS(AJ, "downloadSaved")
P("Tıklanan nokta (yoksa hedef), karenin tarihi, mod, dedektörler ve 4″ içinde Gaia yıldızı olup olmadığıyla birlikte tarayıcının yerel deposuna "
  "(<code>localStorage</code>) yazılır. Her adayın o konuma ortalanmış görünümü açan bir linki vardır. CSV tarayıcıda üretilir; sunucuya hiçbir şey gönderilmez. "
  "Kod adları (<code>saved…</code>) takımın otomatik adaylarından (<code>S.cands</code>) ayrı tutulmuştur.")
H2("11.4 Paylaşma ve gömülü mod")
JS(AJ, "viewUrl")
JS(AJ, "share")
RNG(CS, r"embed=1: only the viewer", r"body.embed .layout")
P("Adreste <code>embed=1</code> varsa <code>body</code>'ye <code>embed</code> sınıfı eklenir ve bu CSS kuralları başlığı, yan panelleri, gelişmiş kontrolleri gizler; "
  "altta tam araca giden bir bağlantı kalır. “Copy embed code” hazır bir <code>&lt;iframe&gt;</code> kodu verir.")
H2("11.5 Küçük eklemeler")
UL("<b>Latest image rozeti:</b> alandaki en yeni SPHEREx görüntüsünün tarihi (arşiv kareleri sayılmaz).",
   "<b>Dizin notu:</b> sayfa açılırken <code>/api/index</code> okunur ve görüntünün altında “Searchable SPHEREx images: up to …” yazar; kullanıcı verinin ne kadar güncel olduğunu görür.",
   "<b>Kayıtta alan adı:</b> alan adı ve görüş alanı ekrandaki sonuçtan (<code>S.result</code>) alınır; yeni bir hedef yüklenirken <code>S.target</code> hemen değiştiği için eskisi yanlış ad yazabiliyordu.",
   "<b>hashchange dinleyicisi:</b> aday linkine tıklanınca sayfa yeniden yüklenmeden o görünüm açılır. <code>initFromHash</code> tarih kutularını her seferinde "
   "adrese göre ayarlar (adreste yoksa boşaltır); yoksa eski tarih aralığı aday görünümüne taşınırdı.",
   "<b>Yalnızca bu alandaki adaylar çizilir:</b> teğet düzlem izdüşümü uzak (örneğin gökyüzünün öbür yüzündeki) bir noktayı da tuvalin içine düşürebilir; "
   "alan merkezine 1°'den uzak adaylar atlanır.",
   "<b>Telefon düzeni:</b> 900 pikselin altında başlık ve rozetler alt alta dizilir, rozetler satır kırar; “Sky context” başlığındaki uzun menü de sayfayı genişletmez.",
   "<b>README:</b> yeni veri sürümünden sonra dizinin ve önbelleğin nasıl yenileneceğini anlatan bölüm.")

# ------------------------------------------------------------------ 12
H1("12. Paralaks izleyici (Track modu)")
H2("12.1 Sorun: medyan, ziyaret içinde hareket edeni siler")
P("Normal kareler bir ziyaretin bütün görüntülerinin piksel medyanıdır (<code>combine_cell</code>). Bu, kozmik ışınları siler; "
  "ama ziyaret sürerken (10–40 gün) yer değiştiren her şeyi de bulanıklaştırır ya da siler. Neptün'ün çok ötesindeki bir cisim "
  "gökyüzünde esas olarak Dünya kendisi hareket ettiği için kayar (paralaks).")
UL("Ölçüm (gerçek ziyaretler): ziyaretler çoğunlukla 10–40 gün sürer, dedektör başına 7–8 görüntü indirilir.",
   "Eris'in Temmuz 2025 ziyaretinde (15 gün) Dünya'nın hareketiyle kayma: 35 AU'da 46 px, 95,6 AU'da 17 px, 300 AU'da 5,4 px, 500 AU'da 3,3 px, 1000 AU'da 1,6 px.",
   "SPHEREx Güneş'e yaklaşık 90° bakarak tarar; bu yönde paralaks hareketi en yavaştır (duraklama noktası). Bu yüzden izleyicinin en çok işe yaradığı aralık birkaç yüz AU'ya kadardır; "
   "daha uzakta medyan cismi silmez, yalnızca birkaç piksel bulanıklaştırır.")
H2("12.2 Model: uzayda sabit nokta + sabit gökyüzü hızı")
P("Cisim, ziyaretin ortasındaki görüntü anında, alanın merkez yönünde, <i>d</i> AU uzaklıkta uzayda sabit bir nokta (P) kabul edilir. "
  "Her görüntünün anındaki Dünya konumundan P'nin yönü hesaplanır ve piksele çevrilir; cismin kendi yörünge hareketi için doğuya ve kuzeye sabit bir ek hız (″/gün) eklenir.")
UL("JPL Horizons ile sınama (40 gün): yalnızca uzaklık modeli 19–138 px yanılırken, uzaklık + sabit hız modelinin en büyük hatası Eris 0,02, Makemake 0,13, Sedna 0,06, Neptün 0,39 px.",
   "Bulunan hızlar her cisim için Ocak ve Temmuz'da aynı çıktı (Eris +1,26 / +2,59″/gün): bu gerçekten cismin yörünge hareketidir. Neptün için hesaplanan 21″/gün, 30 AU'da 5,4 km/s'ye denk gelir (gerçek yörünge hızı).",
   "400–800 AU'da yörünge hızı en fazla ~0,3″/gün: 40 günde 2 pikselden az. Orada uzaklık tek başına yeterlidir.")
H2("12.3 Sunucu: bir ziyaretin tek görüntüleri")
PY("backend/tracker.py", "visit_images")
P("Alan bellekteyse kesitler oradan alınır; değilse yalnızca istenen ziyaretin kesitleri paralel indirilir (bütün alan değil: 81 sn yerine 1,7 sn). "
  "Her kesit <code>reproject_one</code> ile ortak ızgaraya taşınır; her görüntü anındaki Dünya konumu astropy'nin yerleşik efemeridinden hesaplanır (ağa çıkmaz). "
  "Sonuç <code>trk_&lt;anahtar&gt;_&lt;ziyaret&gt;.json</code> olarak saklanır (ziyaret başına ~0,6 MB). Uç nokta: <code>/api/track/{key}/{epoch}</code>.")
H2("12.4 Arayüz: kaydır ve medyan al")
JS(AJ, "trkShifts")
P("Ziyaretin ortadaki görüntüsü referanstır: P = Dünya(referans) + d × merkez yönü. Her görüntü için P − Dünya(t) yönü <code>world2pix</code> ile piksele çevrilir; "
  "ızgarada x batıya doğru büyüdüğü için doğu hızı x'ten çıkarılır.")
JS(AJ, "trackFrame")
UL("Her görüntü, cismin o görüntüdeki yerinden bilinear örneklenir; böylece cisim her görüntüde aynı piksele gelir.",
   "Her dedektörde medyan alınır, sonra dedektörler takımın <code>composite</code>'i gibi toplanıp kareköküne bölünür.",
   "Alanın dışına düşen görüntüler o pikselde atlanır. Bir pikselde en az 3 görüntü (ya da hepsi) aranır; tek bir kozmik ışın sahte kaynak olmasın.")
JS(AJ, "trkNote")
P("Kaydırıcı logaritmiktir (25–4000 AU). Değerler adrese yazılır (<code>&amp;mode=track&amp;dist=35&amp;ve=17.5&amp;vn=-1.2</code>), yani bir tespit bağlantıyla paylaşılabilir. Klavye: T.")
H2("12.5 Gerçek veriyle sınama")
UL("<b>Pluto</b> (V = 14,5, 35 AU), 25 Eylül – 12 Ekim 2025 ziyareti, 8′ alan, 43 görüntü. Ziyaret boyunca 49 piksel yürüdüğü için normal karede yok. "
   "Track modunda Horizons'tan hesaplanan değerlerle (35 AU, +17,53 / −1,16″/gün) tek bir kaynak <b>92σ</b>'ya çıkar; 30 AU'da 24σ, 40 AU'da 30σ, 25 AU'da 8,7σ, 200 AU'da 7,2σ. "
   "Ek hız olmadan 35 AU'da 7,9σ: bu uzaklıkta yörünge hızı gereklidir.",
   "Tepenin konumu (+5, −1 px) Pluto'nun referans görüntü anındaki Horizons konumuyla (+5,4, −0,8 px) yarım pikselden iyi örtüşür. Görüntüde yıldızlar çizgi olur, Pluto tek noktada toplanır.",
   "<b>Eris</b> (V = 18,6, 95,6 AU), Temmuz 2025: dedektör başına ~8 görüntüyle gürültüden ayrılamadı (4,5σ, yanlış uzaklıklarda da benzer tepeler). Sınır izleyicinin değil, görüntü sayısının; "
   "ziyaretteki 114 görüntünün tamamı kullanılırsa derinlik artar.")

# ------------------------------------------------------------------ 13
H1("13. Keşif nereye bildirilir")
P("Yan panelin en altındaki “Found something new? Where discoveries are reported” kartı, kullanıcının yeni bir şey bulduğunu düşündüğünde "
  "onu keşiflerin gerçekten bildirildiği kurumlara yönlendirir. Kart yalnızca HTML'dir; JavaScript kodu yoktur. Araç hiçbir şey kaydetmez, hiçbir yere göndermez.")
P("Araştırmanın sonucu şuydu: NASA'nın “keşfini buraya gir” diye bir formu ya da e-posta adresi yok. Her cisim türünün kendi resmi kanalı var ve resmi isim de o kanaldan gelir; "
  "bulan kişi isim seçemez. Önce konumu, takma adı, bilinen-cisim kontrollerini ve hazır rapor metnini içeren bir form yapıldı. "
  "Sonra ekip, kartın yalnızca kurumlara yönlendirmesine karar verdi ve form kaldırıldı.")
H2("13.1 Türler ve kurumlar")
UL("<b>Hareket eden Güneş Sistemi cismi</b> (asteroit, kuyruklu yıldız, uzak gezegen): IAU Minor Planet Center (MPC). Ölçülmüş konumlar ADES biçiminde, "
   "MPC gözlemevi koduyla gönderilir; kodu olmayan yeni gözlemciler önce kod ister ve bilinen cisimlerde iyi ölçüm gösterir. Pratikte: MPC'ye bildiren bir kulübe, "
   "gözlemevine ya da ekibe gönderin. Kuyruklu yıldız için ayrıca CBAT'a düz metin e-posta (cbatiau@eps.harvard.edu, konu satırında cisim türü). "
   "İsim: numaralandıktan sonra keşfeden önerir, IAU WGSBN onaylar; kuyruklu yıldızlar keşfedenin adını alır.",
   "<b>Kahverengi cüce / hızlı yıldız:</b> resmi kayıt yeri yok. Backyard Worlds: Planet 9 Talk forumunun Science panosu; orada başka verilerle bulunan adaylar da tartışılıyor. "
   "İsim: koordinattan katalog adı (ör. WISEA J110125.95+540052.8); IAU yıldızlara kişi adı vermez.",
   "<b>Değişken yıldız:</b> AAVSO VSX. Kayıt olunur, giriş yapılır, <i>Submit</i> sayfasından yeni yıldız girilir; moderatör inceler. Ani patlama (nova) önce CBAT'a.",
   "<b>Geçici olay</b> (tek ziyarette görünüp hareket etmeyen: süpernova, nova): IAU Transient Name Server (TNS). Hesap istenir (kurum ya da gerekçe sorulur), "
   "<i>Reports → AT report</i>. Sistem “AT 2026abc” gibi ad verir; bulanın verdiği ad “Internal name” alanına yazılabilir.")
P("Bu adımların her biri 15 Kasım 2026'da ilgili sayfa açılarak kontrol edildi: MPC belgeleri, CBAT sayfası (e-posta adresi dahil), TNS kayıt sayfası, "
  "VSX Submit ve Register sayfaları, Backyard Worlds Talk panoları. Kurumlar menülerini değiştirebilir; kartın altında bu tarih yazar.")
RNG(IH, r'<section class="card report" id="reportCard">', r'<div class="rep-cols">')
P("Kartın başlığı (“Found something new? …”) bir düğmedir. Altındaki açıklama paragrafı hep görünür; dört tür ve tarih notu ise "
  "<code>#reportBody</code> içindedir ve sayfa açıldığında gizlidir (<code>hidden</code>). Başlığa basınca açılır, tekrar basınca kapanır; "
  "ok işareti açıkken aşağı döner ve ekran okuyucular için <code>aria-expanded</code> güncellenir. "
  "<code>&lt;details&gt;</code> kullanılmadı, çünkü onda açıklama paragrafı da gizlenirdi.")
P("Paylaşım menüsündeki (“Save as candidate” ile “Copy link” arasında) <b>Report a discovery ↓</b> düğmesi listeyi açar ve sayfayı bu karta kaydırır. "
  "Bu bir <code>#reportCard</code> bağlantısı değildir: adresin <code>#</code> sonrası görünüm ayarlarını tutar ve değişince alan yeniden yüklenir. "
  "Düğme adresi değiştirmeden <code>scrollIntoView</code> ile kaydırır. Yerelde denendi: liste ilk açılışta kapalı, başlıkla açılıp kapanıyor; "
  "menü düğmesi listeyi açıp kartın üst kenarını ekranın en üstüne getiriyor, adres ve yüklü alan aynı kalıyor.")
RNG(AJ, r'"where discoveries are reported": the list under', r'\$\("reportGo"\)\.onclick')
H2("13.2 Kartın yeri")
RNG(CS, r'^/\* "where discoveries are reported"', r"^\.rep-kind \.name-rule")
P("SkyBlink tasarımı yan paneldeki kartları <b>sıra numarasıyla</b> yerleştirir (<code>.side &gt; section:nth-child(4)</code> gibi). Araya yeni bir kart girerse "
  "diğerlerinin yeri kayar ve sol tarafta boşluk kalır. Bu yüzden kart en sona konur ve kendi tam genişlikteki satırına yerleşir (masaüstünde 6. satır, telefonda 8.). "
  "İçindeki dört tür masaüstünde iki sütun, telefonda tek sütundur.")
NOTE("Aynı çalışmada SkyBlink'in telefon düzeninde bir hata bulundu: telefon kuralı <code>.side &gt; section { grid-column: 1 }</code>, masaüstündeki "
     "<code>:nth-child()</code> kurallarından daha zayıf olduğu için telefonda ikinci bir sütun oluşuyor ve kartlar 28 piksele sıkışıyordu. "
     "Telefon bölümüne aynı özgüllükte bir kural (<code>.side &gt; section:nth-child(n)</code>) eklenerek düzeltildi; 390 piksel genişlikte bütün kartlar ekran genişliğinde.")

# ------------------------------------------------------------------ 14
H1("14. Diğer dosyalar")
RNG("backend/targets.json", r'"id": "wise0855"', r'"note"')
P("Hazır hedeflerin konumu, öz hareketi ve bu değerlerin ait olduğu yıl.")
RNG("scripts/warm_cache.py", r"^fovs = ", r"FAILED")
P("Hazır hedefleri önceden hesaplayıp <code>data/results/</code> klasörüne yazar; demo sırasında bu hedefler anında açılır.")
RNG("render.yaml", r"^services:", r"value: ")
P("Render'a siteyi nasıl kuracağını söyler. <code>autoDeploy: true</code> olduğu için <code>main</code> dalına her gönderim canlı siteyi günceller.")

# ------------------------------------------------------------------ 15
H1("15. Bilinen sınırlar")
UL("Yeni bir alanın tam yüklemesi ücretli küçük sunucuda ~1 dakika sürer; ilk kareler çok daha önce gelir.",
   "Dizin kurulduğu andaki görüntüleri bilir; yeni veri için <code>scripts/list_s3.py</code> ve <code>scripts/build_index.py</code> çalıştırılıp dizin dosyası commit'lenmelidir (otomatik değildir).",
   "Çok parlak yıldızlar doymuştur: tayfları yaklaşık, ışık eğrileri yalnızca görelidir.",
   "Otomatik aday kutuları ipucudur; demo alanlarında ayarlanmıştır, başka alanlarda yanlış alarm oranı ölçülmedi.",
   "2MASS ve WISE başka teleskoplardır: konumları karşılaştırın, parlaklıklarını değil.",
   "Paralaks izleyici yalnızca indirilen görüntüleri kullanır (dedektör başına ~8); sönük cisimler (Eris gibi) için yetmez. Ziyaret içinde çalışır; ziyaretler arası 6 ayda uzak bir cisim alanın dışına çıkar. "
   "Birkaç yüz AU'nun ötesinde kazanç azalır, çünkü SPHEREx'in bakış yönünde paralaks hareketi en yavaştır.",
   "Aday listesi yalnızca o tarayıcıda durur; tarayıcı verisi silinirse kaybolur.",
   "“Where discoveries are reported” kartı yalnızca yönlendirir: bir keşfi doğrulamaz, bildirimi kullanıcı kendisi yapar. "
   "Adımlar 15 Kasım 2026'daki sayfalara göre yazıldı.")

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.2pt; line-height: 1.5; color: #1b2330; }
h1 { font-size: 17pt; color: #0b3a66; border-bottom: 2px solid #0b3a66; padding-bottom: 3px; margin: 26px 0 10px; page-break-after: avoid; }
h2 { font-size: 12.5pt; color: #0b3a66; margin: 18px 0 6px; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 14px 0 4px; page-break-after: avoid; }
p { margin: 6px 0; } ul { margin: 6px 0 8px; padding-left: 20px; } li { margin-bottom: 3px; }
code { font-family: Consolas, monospace; font-size: 9.2pt; background: #eef2f7; padding: 0 3px; border-radius: 3px; }
.code { margin: 8px 0 10px; border: 1px solid #c9d3df; border-radius: 5px; overflow: hidden; }
.cap { background: #0b3a66; color: #fff; font: 8.3pt Consolas, monospace; padding: 3px 8px; }
pre { margin: 0; padding: 7px 9px; background: #f6f8fb; font: 7.9pt/1.38 Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
.more { font-size: 8.3pt; color: #5b6878; padding: 2px 9px 4px; background: #f6f8fb; font-style: italic; }
.note { background: #fff6e0; border-left: 4px solid #e0a020; padding: 6px 10px; }
.cover { padding: 60px 0 30px; page-break-after: always; }
.kicker { color: #5b6878; letter-spacing: .5px; font-size: 10pt; }
.title { font-size: 32pt; font-weight: 700; color: #0b3a66; margin: 8px 0 2px; }
.sub { font-size: 14pt; color: #33465c; margin-bottom: 26px; }
"""
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(f"<!doctype html><html lang='tr'><head><meta charset='utf-8'><title>SPHEREx Time Machine: Kod Anlatımı</title>"
               f"<style>{CSS}</style></head><body>{''.join(parts)}</body></html>", encoding="utf-8")
print(f"Wrote {OUT} ({sum(1 for p in parts if p.startswith('<div class=' + chr(34) + 'code'))} code blocks)")
