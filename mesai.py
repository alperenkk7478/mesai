"""
Mesai Hesaplama Aracı  –  v2
==============================
Düzeltmeler:
  - Öğle arası ve diğer molalar ayrı girdi
  - Default 0 dk
  - "Normal mesai (8 saat)" kategorisi eklendi
  - Kesinti tablosu → ŞİRKETTE BULUNMA süresine göre (net değil)
  - 11 saat kategorisi = şirkette bulunma süresi
  - Örnek doğrulama: 08:00 giriş + 30 dk kesinti → 15:30 çıkış ✓
"""

import streamlit as st
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# SABITLER
# ─────────────────────────────────────────────

# Giriş filtresi
ENTRY_ROUND_START  = "07:00"
ENTRY_ROUND_END    = "08:00"
ENTRY_CANONICAL    = "08:00"

# Çıkış filtresi
EXIT_ROUND_START   = "17:00"
EXIT_ROUND_END     = "18:00"
EXIT_CANONICAL     = "17:00"

# Öğle arası
LUNCH_FREE_MIN     = 60          # ücretsiz öğle süresi (dk)

# Kesinti tablosu — eşik = ŞİRKETTE BULUNMA süresi (saat), kesinti dakika
# Mantık: şirkette ne kadar kaldın? → o kadar kesinti uygulanır
DEDUCTION_TABLE = [
    (4.0,            15),   # ≤ 4 sa bulunma  → 15 dk
    (7.5,            30),   # ≤ 7.5 sa         → 30 dk
    (11.0,           60),   # ≤ 11 sa           → 60 dk
    (float("inf"),   90),   # > 11 sa           → 90 dk
]

# Hedef kategoriler: etiket → şirkette bulunma süresi (saat)
# "Normal mesai" = 08:00-17:00 = 9 saat bulunma (8 sa net)
TARGET_CATEGORIES = {
    "4 saat (şirkette bulunma)"    : 4.0,
    "7,5 saat (şirkette bulunma)"  : 7.5,
    "Normal mesai – 8 saat net"    : 9.0,   # 9 sa bulunma = 8 sa net (60 dk kesinti)
    "11 saat (şirkette bulunma)"   : 11.0,
    "11+ saat (şirkette bulunma)"  : 12.0,
}

# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def parse_hhmm(s: str) -> datetime:
    return datetime.strptime(s, "%H:%M").replace(year=2000, month=1, day=1)

def format_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def apply_entry_filter(raw: datetime) -> datetime:
    """07:00–08:00 arası giriş → 08:00 kabul; öncesi → gerçek."""
    if parse_hhmm(ENTRY_ROUND_START) <= raw <= parse_hhmm(ENTRY_ROUND_END):
        return parse_hhmm(ENTRY_CANONICAL)
    return raw

def apply_exit_filter(raw: datetime) -> datetime:
    """17:00–18:00 arası çıkış → 17:00 kabul; sonrası → gerçek."""
    if parse_hhmm(EXIT_ROUND_START) <= raw <= parse_hhmm(EXIT_ROUND_END):
        return parse_hhmm(EXIT_CANONICAL)
    return raw

def calc_lunch_deduction(lunch_min: int) -> int:
    """İlk 60 dk ücretsiz; fazlası kesilir."""
    return max(0, lunch_min - LUNCH_FREE_MIN)

def calc_table_deduction(presence_hours: float) -> int:
    """Şirkette bulunma süresine göre kesinti tablosundan değer döndür."""
    for threshold, deduction in DEDUCTION_TABLE:
        if presence_hours <= threshold:
            return deduction
    return DEDUCTION_TABLE[-1][1]

def hours_to_label(hours: float) -> str:
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    return f"{h}sa {m:02d}dk"

# ─────────────────────────────────────────────
# ANA HESAPLAMA MOTORU
# ─────────────────────────────────────────────
#
# MANTIK:
#   presence_hours = hedef şirkette bulunma süresi
#   table_deduction = kesinti tablosundan (bulunma süresine göre)
#   lunch_extra = max(0, öğle_dk - 60)   ← sadece aşan kısım
#   other_break = diğer molalar (tamamı kesilir)
#   toplam_kesinti = table_deduction + lunch_extra + other_break
#   net_calisma = presence_hours - toplam_kesinti / 60
#   çıkış = giriş + presence_hours + (lunch_extra + other_break) / 60
#          (tablo kesintisi zaten presence_hours içine gömülü DEĞİL,
#           çıkış saatini etkilemez — sadece "net mesai" raporlamasında görünür)
#
# ÖRNEK DOĞRULAMA:
#   Giriş: 08:00, mola: 0, hedef: 7.5 sa bulunma
#   table_deduction(7.5) = 30 dk
#   Çıkış = 08:00 + 7.5 sa = 15:30  ✓  (filtre: 15:30 < 17:00 → geçmez, ham kullanılır)
#   Net çalışma = 7.5 - 30/60 = 7.0 sa

def calculate(
    raw_entry_str  : str,
    lunch_min      : int,
    other_min      : int,
    target_label   : str,
) -> dict:

    presence_hours = TARGET_CATEGORIES[target_label]
    raw_entry      = parse_hhmm(raw_entry_str)
    eff_entry      = apply_entry_filter(raw_entry)

    # Kesintiler
    lunch_extra_min  = calc_lunch_deduction(lunch_min)   # öğle aşımı
    other_deduct_min = other_min                          # diğer molalar tamamı
    table_deduct_min = calc_table_deduction(presence_hours)

    total_extra_min  = lunch_extra_min + other_deduct_min  # çıkışı geciktiren ekstralar
    total_deduct_min = table_deduct_min + lunch_extra_min + other_deduct_min

    # Çıkış = giriş + hedef bulunma süresi + extra dışarıda geçirilen süre
    raw_exit_min  = int(presence_hours * 60) + total_extra_min
    raw_exit      = eff_entry + timedelta(minutes=raw_exit_min)
    eff_exit      = apply_exit_filter(raw_exit)

    net_work_min  = int(presence_hours * 60) - table_deduct_min
    # (lunch ve other zaten dışarıda geçirildi, net çalışmaya dahil değil)

    # Filtre kaybı: çıkış filtresi ham saati geri çektiyse kaybedilen dakika
    filter_loss_min = int((raw_exit - eff_exit).total_seconds() // 60)

    return {
        "raw_entry"          : format_hhmm(raw_entry),
        "eff_entry"          : format_hhmm(eff_entry),
        "entry_adjusted"     : raw_entry != eff_entry,
        "presence_hours"     : presence_hours,
        "lunch_min"          : lunch_min,
        "lunch_extra_min"    : lunch_extra_min,
        "other_min"          : other_deduct_min,
        "table_deduct_min"   : table_deduct_min,
        "total_deduct_min"   : total_deduct_min,
        "raw_exit"           : format_hhmm(raw_exit),
        "eff_exit"           : format_hhmm(eff_exit),
        "exit_adjusted"      : raw_exit != eff_exit,
        "filter_loss_min"    : filter_loss_min,
        "net_work_min"       : net_work_min,
        "net_work_hours"     : net_work_min / 60,
        "is_valid"           : eff_exit > eff_entry,
    }


# ─────────────────────────────────────────────
# GERÇEKLEŞEN MESAİ HESAPLAMA MOTORU
# ─────────────────────────────────────────────
#
# Kullanıcı gerçek çıkış saatini girince:
#   1. Giriş + çıkış filtrelerini uygula
#   2. Şirkette bulunma süresi = eff_exit - eff_entry  (dakika)
#   3. Tablo kesintisini bulunma süresine göre bul
#   4. Öğle ve diğer mola kesintilerini uygula
#   5. Net çalışma = bulunma - tablo_kesinti
#      (lunch_extra ve other zaten dışarıda geçti, net'e dahil değil)

def calculate_actual(
    raw_entry_str  : str,
    raw_exit_str   : str,
    lunch_min      : int,
    other_min      : int,
) -> dict:

    raw_entry = parse_hhmm(raw_entry_str)
    raw_exit  = parse_hhmm(raw_exit_str)

    eff_entry = apply_entry_filter(raw_entry)
    eff_exit  = apply_exit_filter(raw_exit)

    if eff_exit <= eff_entry:
        return {"is_valid": False}

    # Bulunma süresi (dakika & saat)
    presence_min   = int((eff_exit - eff_entry).total_seconds() // 60)
    presence_hours = presence_min / 60

    # Kesintiler
    lunch_extra_min  = calc_lunch_deduction(lunch_min)
    other_deduct_min = other_min
    table_deduct_min = calc_table_deduction(presence_hours)
    total_deduct_min = table_deduct_min + lunch_extra_min + other_deduct_min

    # Net çalışma = bulunma − tablo kesintisi
    # (lunch_extra ve other zaten şirket dışında geçirildi)
    net_work_min   = presence_min - table_deduct_min
    filter_loss_min = int((raw_exit - eff_exit).total_seconds() // 60)

    # Hangi mesai kategorisine denk geliyor?
    matched_category = None
    for label, cat_hours in TARGET_CATEGORIES.items():
        if abs(presence_hours - cat_hours) < 0.01:
            matched_category = label
            break

    return {
        "is_valid"           : True,
        "raw_entry"          : format_hhmm(raw_entry),
        "eff_entry"          : format_hhmm(eff_entry),
        "entry_adjusted"     : raw_entry != eff_entry,
        "raw_exit"           : format_hhmm(raw_exit),
        "eff_exit"           : format_hhmm(eff_exit),
        "exit_adjusted"      : raw_exit != eff_exit,
        "filter_loss_min"    : filter_loss_min,
        "presence_min"       : presence_min,
        "presence_hours"     : presence_hours,
        "lunch_min"          : lunch_min,
        "lunch_extra_min"    : lunch_extra_min,
        "other_min"          : other_deduct_min,
        "table_deduct_min"   : table_deduct_min,
        "total_deduct_min"   : total_deduct_min,
        "net_work_min"       : net_work_min,
        "net_work_hours"     : net_work_min / 60,
        "matched_category"   : matched_category,
    }


# ─────────────────────────────────────────────
# STREAMLIT ARAYÜZÜ
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Mesai Hesaplama Aracı",
    page_icon="🕐",
    layout="wide",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .hero {
        background: linear-gradient(135deg, #1a1f36 0%, #2d3561 100%);
        border-radius: 16px;
        padding: 28px 32px 22px;
        margin-bottom: 28px;
        color: white;
    }
    .hero h1 { margin: 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.5px; }
    .hero p  { margin: 6px 0 0; font-size: 0.9rem; opacity: 0.7; }

    .card-title {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #8b92a5;
        margin-bottom: 10px;
    }
    .rule-badge {
        display: inline-block;
        background: #f0f3ff;
        color: #3d4fd6;
        border-radius: 6px;
        padding: 3px 9px;
        font-size: 0.74rem;
        font-weight: 500;
        margin: 3px 3px 3px 0;
    }

    [data-testid="metric-container"] {
        background: #f8f9fc;
        border: 1px solid #e8eaf0;
        border-radius: 12px;
        padding: 14px 18px !important;
    }
    [data-testid="metric-container"] label {
        font-size: 0.70rem !important;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #8b92a5 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1a1f36 !important;
    }

    .exit-time-box {
        background: linear-gradient(135deg, #2d3561, #4a6cf7);
        border-radius: 14px;
        padding: 24px 28px;
        color: white;
        text-align: center;
        margin-bottom: 12px;
    }
    .exit-time-box .label { font-size: 0.72rem; opacity: 0.75; letter-spacing: 0.1em; text-transform: uppercase; }
    .exit-time-box .time  { font-size: 3.4rem; font-weight: 700; letter-spacing: -1px; line-height: 1.1; }
    .exit-time-box .sub   { font-size: 0.8rem; opacity: 0.65; margin-top: 6px; }

    [data-testid="stSidebar"] { background: #f4f5f9; }

    .warn-box {
        background: #fff4e5;
        border: 1px solid #ffb84d;
        border-radius: 10px;
        padding: 14px 18px;
        color: #7a4800;
        font-size: 0.88rem;
    }
    .adj-note {
        background: #eef2ff;
        border-left: 3px solid #4a6cf7;
        border-radius: 0 8px 8px 0;
        padding: 8px 14px;
        font-size: 0.8rem;
        color: #3d4fd6;
        margin-top: 10px;
    }
    .filter-loss-box {
        background: #fff8ec;
        border: 1.5px solid #f59e0b;
        border-radius: 10px;
        padding: 14px 18px;
        margin-top: 12px;
        color: #78350f;
        font-size: 0.86rem;
        line-height: 1.55;
    }
    .filter-loss-box strong { color: #92400e; }
    .filter-loss-box .fl-title {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: #b45309;
        margin-bottom: 6px;
    }
    .actual-net-box {
        background: linear-gradient(135deg, #064e3b, #065f46);
        border-radius: 14px;
        padding: 24px 28px;
        color: white;
        text-align: center;
        margin-bottom: 12px;
    }
    .actual-net-box .label { font-size: 0.72rem; opacity: 0.75; letter-spacing: 0.1em; text-transform: uppercase; }
    .actual-net-box .time  { font-size: 3.4rem; font-weight: 700; letter-spacing: -1px; line-height: 1.1; }
    .actual-net-box .sub   { font-size: 0.8rem; opacity: 0.65; margin-top: 6px; }
    .mode-badge-plan {
        display: inline-block;
        background: #eef2ff; color: #3730a3;
        border-radius: 20px; padding: 3px 12px;
        font-size: 0.73rem; font-weight: 600;
        margin-bottom: 14px;
    }
    .mode-badge-actual {
        display: inline-block;
        background: #d1fae5; color: #065f46;
        border-radius: 20px; padding: 3px 12px;
        font-size: 0.73rem; font-weight: 600;
        margin-bottom: 14px;
    }
    .section-sep { margin: 18px 0 10px; border: none; border-top: 1px solid #e0e3ed; }
</style>
""", unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🕐 Mesai Hesaplama Aracı</h1>
  <p>Giriş saatinizi, mola sürelerinizi ve hedef kategoriyi girin — çıkış saatinizi otomatik hesaplayalım.</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Parametreler")
    st.markdown("---")

    entry_time = st.time_input(
        "Giriş Saati",
        value=datetime.strptime("08:00", "%H:%M").time(),
        step=60,
        help="Kartınızı okuttuğunuz / kapıdan geçtiğiniz saat.",
    )

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)
    st.markdown("**🥗 Öğle Arası (11:30–13:30)**")
    lunch_min = st.number_input(
        "Öğle arası süresi (dakika)",
        min_value=0, max_value=180, value=0, step=5,
        help="Sadece öğle arasına ait dışarıda geçirilen süre. "
             "İlk 60 dk ücretsizdir; fazlası mesaiden kesilir.",
    )

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)
    st.markdown("**☕ Diğer Şirket Dışı Çıkışlar**")
    other_min = st.number_input(
        "Diğer çıkış süresi (dakika)",
        min_value=0, max_value=240, value=0, step=5,
        help="Öğle dışı tüm dışarı çıkışların toplamı. Tamamı mesaiden kesilir.",
    )

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)
    target_label = st.selectbox(
        "Hedeflenen Mesai Kategorisi",
        options=list(TARGET_CATEGORIES.keys()),
        index=2,          # "Normal mesai" varsayılan
        help="Ulaşmak istediğiniz mesai seviyesi. "
             "'Normal mesai' = 08:00–17:00 = 9 sa şirkette, 8 sa net.",
    )

    st.markdown('<hr class="section-sep">', unsafe_allow_html=True)
    st.markdown("**🚪 Gerçek Çıkış Saati** *(opsiyonel)*")
    use_actual_exit = st.checkbox(
        "Çıkış saatimi girdim, net mesaimi hesapla",
        value=False,
        help="İşaretlerseniz sistem 'çıkış saati hesaplama' yerine "
             "'gerçekleşen net mesai' moduna geçer.",
    )
    actual_exit_time = None
    if use_actual_exit:
        actual_exit_time = st.time_input(
            "Gerçek Çıkış Saati",
            value=datetime.strptime("17:00", "%H:%M").time(),
            step=60,
            help="Kartınızı okuttuğunuz / kapıdan çıktığınız gerçek saat.",
        )

    st.markdown("---")
    st.markdown("""
    <div class="card-title">Sabit Kurallar</div>
    <span class="rule-badge">07:00–08:00 → 08:00</span>
    <span class="rule-badge">17:00–18:00 → 17:00</span>
    <span class="rule-badge">60 dk ücretsiz öğle</span>
    <span class="rule-badge">≤4sa → 15dk</span>
    <span class="rule-badge">≤7.5sa → 30dk</span>
    <span class="rule-badge">≤11sa → 60dk</span>
    <span class="rule-badge">&gt;11sa → 90dk</span>
    """, unsafe_allow_html=True)

# ── Hesaplama ─────────────────────────────────
entry_str = entry_time.strftime("%H:%M")

if use_actual_exit and actual_exit_time is not None:
    # ══ MOD: Gerçekleşen Mesai ══
    actual_exit_str = actual_exit_time.strftime("%H:%M")
    ar = calculate_actual(
        raw_entry_str = entry_str,
        raw_exit_str  = actual_exit_str,
        lunch_min     = lunch_min,
        other_min     = other_min,
    )

    col_main, col_detail = st.columns([1, 1.65], gap="large")

    with col_main:
        st.markdown('<div class="mode-badge-actual">✅ Gerçekleşen Mesai Modu</div>', unsafe_allow_html=True)

        if not ar["is_valid"]:
            st.markdown("""
            <div class="warn-box">
            ⚠️ <strong>Geçersiz:</strong> Çıkış saati giriş saatinden önce.
            Saatleri kontrol edin.
            </div>
            """, unsafe_allow_html=True)
        else:
            exit_sub = (
                f"Ham: {ar['raw_exit']} → filtre uygulandı"
                if ar["exit_adjusted"] else "Çıkış filtresi uygulanmadı"
            )
            st.markdown(f"""
            <div class="actual-net-box">
              <div class="label">Net Çalışma Süresi</div>
              <div class="time">{hours_to_label(ar['net_work_hours'])}</div>
              <div class="sub">Çıkış: {ar['eff_exit']} &nbsp;|&nbsp; {exit_sub}</div>
            </div>
            """, unsafe_allow_html=True)

            # Filtre kaybı uyarısı
            if ar["exit_adjusted"] and ar["filter_loss_min"] > 0:
                loss = ar["filter_loss_min"]
                actual_net_min = ar["net_work_min"] - loss
                ah, am = divmod(actual_net_min, 60)
                st.markdown(f"""
                <div class="filter-loss-box">
                  <div class="fl-title">⚠️ Çıkış Filtresi Nedeniyle Eksik Mesai</div>
                  Ham çıkış saatiniz <strong>{ar['raw_exit']}</strong> iken
                  <strong>17:00–18:00 filtresi</strong> nedeniyle <strong>{ar['eff_exit']}</strong>
                  olarak kaydedildi.<br>
                  Bu durum <strong>{loss} dakika</strong> mesai kaybına yol açıyor.<br><br>
                  Yukarıdaki net mesai filtrelenmiş saate göre hesaplanmıştır.<br><br>
                  💡 <em>HR ile telafi talebinde bulunabilirsiniz.</em>
                </div>
                """, unsafe_allow_html=True)

            if ar["entry_adjusted"]:
                st.markdown(f"""
                <div class="adj-note">
                ℹ️ Giriş <strong>{ar['raw_entry']}</strong>, 07:00–08:00 aralığında olduğundan
                <strong>{ar['eff_entry']}</strong> kabul edildi.
                </div>
                """, unsafe_allow_html=True)

    with col_detail:
        st.markdown('<div class="card-title">Hesaplama Detayı</div>', unsafe_allow_html=True)

        d1, d2 = st.columns(2)
        d1.metric("Efektif Giriş",     ar["eff_entry"])
        d2.metric("Efektif Çıkış",     ar["eff_exit"])

        d3, d4 = st.columns(2)
        d3.metric(
            "Şirkette Bulunma",
            hours_to_label(ar["presence_hours"]),
            help="Efektif giriş ile efektif çıkış arasındaki süre.",
        )
        d4.metric(
            "Tablo Kesintisi",
            f"{ar['table_deduct_min']} dk",
            help="Bulunma süresine göre kesinti tablosundan.",
        )

        d5, d6 = st.columns(2)
        d5.metric(
            "Öğle Aşım Kesintisi",
            f"{ar['lunch_extra_min']} dk",
            help=f"Öğle: {ar['lunch_min']} dk — İlk 60 dk ücretsiz.",
        )
        d6.metric(
            "Diğer Mola Kesintisi",
            f"{ar['other_min']} dk",
            help="Diğer çıkışların tamamı kesilir.",
        )

        d7, d8 = st.columns(2)
        d7.metric("Toplam Kesinti",    f"{ar['total_deduct_min']} dk")
        d8.metric("Net Çalışma",       hours_to_label(ar["net_work_hours"]))

        if ar["filter_loss_min"] > 0:
            st.markdown(
                f"🟠 **Filtre kaybı:** **{ar['filter_loss_min']} dk** sisteme yansımadı. "
                f"Ham: {ar['raw_exit']} → Kayıtlı: {ar['eff_exit']}",
            )

else:
    # ══ MOD: Planlama (Çıkış Hesaplama) ══
    result = calculate(
        raw_entry_str = entry_str,
        lunch_min     = lunch_min,
        other_min     = other_min,
        target_label  = target_label,
    )

    col_main, col_detail = st.columns([1, 1.65], gap="large")

    with col_main:
        st.markdown('<div class="mode-badge-plan">🗓️ Planlama Modu</div>', unsafe_allow_html=True)

        if not result["is_valid"]:
            st.markdown("""
            <div class="warn-box">
            ⚠️ <strong>Geçersiz hesaplama:</strong> Hesaplanan çıkış saati giriş saatinden önce.
            Lütfen giriş saatini veya mola sürelerini kontrol edin.
            </div>
            """, unsafe_allow_html=True)
        else:
            sub_text = (
                f"Ham: {result['raw_exit']} → filtre uygulandı"
                if result["exit_adjusted"]
                else "Çıkış filtresi uygulanmadı"
            )
            st.markdown(f"""
            <div class="exit-time-box">
              <div class="label">Hesaplanan Çıkış Saati</div>
              <div class="time">{result['eff_exit']}</div>
              <div class="sub">{sub_text}</div>
            </div>
            """, unsafe_allow_html=True)

        # Filtre kaybı uyarısı
        if result["exit_adjusted"] and result["filter_loss_min"] > 0:
            loss = result["filter_loss_min"]
            actual_net_min = result["net_work_min"] - loss
            ah, am = divmod(actual_net_min, 60)
            st.markdown(f"""
            <div class="filter-loss-box">
              <div class="fl-title">⚠️ Çıkış Filtresi Nedeniyle Eksik Mesai</div>
              Ham çıkış saatiniz <strong>{result['raw_exit']}</strong> iken sistem
              <strong>17:00–18:00 filtresi</strong> nedeniyle <strong>{result['eff_exit']}</strong>
              olarak kaydedildi.<br>
              Bu durum <strong>{loss} dakika</strong> mesai kaybına yol açıyor.<br><br>
              Hedef net çalışma: <strong>{hours_to_label(result['net_work_hours'])}</strong> &nbsp;→&nbsp;
              Gerçekleşen net çalışma: <strong>{ah}sa {am:02d}dk</strong><br><br>
              💡 <em>Bu farkı kapatmak için yarın <strong>{loss} dakika erken girmenizi</strong>
              veya HR ile telafi talebinde bulunmanızı öneririz.</em>
            </div>
            """, unsafe_allow_html=True)

        if result["entry_adjusted"]:
            st.markdown(f"""
            <div class="adj-note">
            ℹ️ Giriş <strong>{result['raw_entry']}</strong>, 07:00–08:00 aralığında olduğundan
            <strong>{result['eff_entry']}</strong> kabul edildi.
            </div>
            """, unsafe_allow_html=True)

    with col_detail:
        st.markdown('<div class="card-title">Hesaplama Detayı</div>', unsafe_allow_html=True)

        r1, r2 = st.columns(2)
        r1.metric("Efektif Giriş",        result["eff_entry"])
        r2.metric(
            "Şirkette Bulunma",
            hours_to_label(result["presence_hours"]),
            help="Hedeflenen kapıdan-kapıya süre.",
        )

        r3, r4 = st.columns(2)
        r3.metric(
            "Öğle Aşım Kesintisi",
            f"{result['lunch_extra_min']} dk",
            help=f"Öğle: {result['lunch_min']} dk — İlk 60 dk ücretsiz, aşan kesilir.",
        )
        r4.metric(
            "Diğer Mola Kesintisi",
            f"{result['other_min']} dk",
            help="Diğer çıkışların tamamı kesilir.",
        )

        r5, r6 = st.columns(2)
        r5.metric(
            "Tablo Kesintisi",
            f"{result['table_deduct_min']} dk",
            help="Şirkette bulunma süresine göre kesinti tablosundan.",
        )
        r6.metric(
            "Toplam Kesinti",
            f"{result['total_deduct_min']} dk",
        )

        r7, r8 = st.columns(2)
        r7.metric(
            "Net Çalışma Süresi",
            hours_to_label(result["net_work_hours"]),
            help="Şirkette bulunma − tablo kesintisi.",
        )
        r8.metric("Çıkış Saati", result["eff_exit"])

        if result["filter_loss_min"] > 0:
            st.markdown(
                f"🟠 **Filtre kaybı:** Çıkış filtresi nedeniyle "
                f"**{result['filter_loss_min']} dk** mesai sisteme yansımadı. "
                f"Ham çıkış: {result['raw_exit']} → Kayıtlı: {result['eff_exit']}",
            )

# ── Kural / Tablo Expander ───────────────────
st.markdown("---")
with st.expander("📋 Kesinti Tablosu & Kural Özeti", expanded=False):
    tc1, tc2 = st.columns(2)

    with tc1:
        st.markdown("**Kesinti Tablosu**  *(şirkette bulunma süresine göre)*")
        st.markdown("""
| Şirkette Bulunma | Tablo Kesintisi |
|---|---|
| ≤ 4 saat | 15 dakika |
| 4 – 7,5 saat | 30 dakika |
| 7,5 – 11 saat | 60 dakika |
| > 11 saat | 90 dakika |
""")
        st.caption("Örnek: 08:00 giriş + 7,5 sa bulunma = **15:30 çıkış** → 30 dk tablo kesintisi → 7 sa net çalışma ✓")

    with tc2:
        st.markdown("**Giriş / Çıkış Filtresi**")
        st.markdown("""
| Giriş Aralığı | Kabul |
|---|---|
| 07:00 – 08:00 | **08:00** |
| 07:00 öncesi | Gerçek giriş |

| Çıkış Aralığı | Kabul |
|---|---|
| 17:00 – 18:00 | **17:00** |
| 18:00 sonrası | Gerçek çıkış |
""")

    st.info(
        "**Öğle Arası:** İlk 60 dk ücretsizdir; aşan kısım kesilir.  \n"
        "**Diğer Molalar:** Tamamı mesaiden düşülür, çıkış saati o kadar ötelenir.  \n"
        "**Normal Mesai (8 sa net):** 08:00–17:00 = 9 sa şirkette − 60 dk tablo = 8 sa net.",
        icon="📌",
    )
