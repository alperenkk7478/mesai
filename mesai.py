"""
Mesai Hesaplama Aracı
=====================
Sabit kurallar değişkenlerde tanımlı, modüler yapı.
"""

import streamlit as st
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# SABITLER
# ─────────────────────────────────────────────

# Giriş filtresi
ENTRY_ROUND_START = "07:00"   # Bu saatten erken giriş → gerçek giriş kullanılır
ENTRY_ROUND_END   = "08:00"   # Bu saatler arasında giriş → 08:00 kabul
ENTRY_CANONICAL   = "08:00"   # Yuvarlanmış giriş saati

# Çıkış filtresi
EXIT_ROUND_START  = "17:00"   # Bu saatler arasında çıkış → 17:00 kabul
EXIT_ROUND_END    = "18:00"   # Bu saatten sonra çıkış → gerçek çıkış kullanılır
EXIT_CANONICAL    = "17:00"   # Yuvarlanmış çıkış saati

# Öğle arası
LUNCH_START       = "11:30"
LUNCH_END         = "13:30"
LUNCH_FREE_MIN    = 60        # Ücretsiz öğle arası (dakika)

# Kesinti tablosu (eşik değerleri saat cinsinden, kesinti dakika cinsinden)
DEDUCTION_TABLE = [
    (4.0,   15),   # ≤ 4 saat  → 15 dk
    (7.5,   30),   # ≤ 7.5 saat → 30 dk
    (11.0,  60),   # ≤ 11 saat  → 60 dk
    (float("inf"), 90),  # > 11 saat → 90 dk
]

# Hedef mesai kategorileri (saat)
TARGET_CATEGORIES = {
    "4 saat"    : 4.0,
    "7,5 saat"  : 7.5,
    "11 saat"   : 11.0,
    "11+ saat"  : 12.0,
}

# ─────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────

def parse_hhmm(s: str) -> datetime:
    """'HH:MM' string → datetime (bugünün tarihi ile)"""
    return datetime.strptime(s, "%H:%M").replace(
        year=2000, month=1, day=1
    )


def format_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def apply_entry_filter(raw_entry: datetime) -> datetime:
    """Giriş saatini kurala göre düzelt."""
    t_start = parse_hhmm(ENTRY_ROUND_START)
    t_end   = parse_hhmm(ENTRY_ROUND_END)
    t_canon = parse_hhmm(ENTRY_CANONICAL)

    if t_start <= raw_entry <= t_end:
        return t_canon          # 07:00-08:00 → 08:00
    return raw_entry            # Öncesi → gerçek giriş


def apply_exit_filter(raw_exit: datetime) -> datetime:
    """Çıkış saatini kurala göre düzelt."""
    t_start = parse_hhmm(EXIT_ROUND_START)
    t_end   = parse_hhmm(EXIT_ROUND_END)
    t_canon = parse_hhmm(EXIT_CANONICAL)

    if t_start <= raw_exit <= t_end:
        return t_canon          # 17:00-18:00 → 17:00
    return raw_exit             # Sonrası → gerçek çıkış


def calc_lunch_deduction(total_outside_min: int) -> int:
    """
    Öğle arası kesintisi:
    - İlk 60 dk ücretsiz
    - Aşan kısım kesintiye eklenir
    """
    if total_outside_min <= LUNCH_FREE_MIN:
        return 0
    return total_outside_min - LUNCH_FREE_MIN


def calc_break_deduction_table(net_work_hours: float) -> int:
    """Kesinti tablosundan net çalışma süresine göre kesinti dakikasını döndür."""
    for threshold, deduction in DEDUCTION_TABLE:
        if net_work_hours <= threshold:
            return deduction
    return DEDUCTION_TABLE[-1][1]


def hours_to_hhmm(hours: float) -> str:
    """Ondalık saat → 'Xsa Ydak' formatı"""
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    return f"{h}sa {m:02d}dk"


def calculate(
    raw_entry_str: str,
    total_outside_min: int,
    target_hours: float,
) -> dict:
    """
    Ana hesaplama motoru.

    Parametreler
    ─────────────
    raw_entry_str      : Kullanıcının girdiği saat (HH:MM)
    total_outside_min  : Dışarıda geçirilen toplam dakika (öğle + diğer molalar)
    target_hours       : Hedef mesai süresi (saat)

    Döndürür
    ────────
    Hesaplama sonuçlarını içeren sözlük.
    """
    raw_entry = parse_hhmm(raw_entry_str)

    # 1. Giriş filtresini uygula
    effective_entry = apply_entry_filter(raw_entry)

    # 2. Öğle kesintisini hesapla
    lunch_deduction_min = calc_lunch_deduction(total_outside_min)

    # 3. Hedeften kesintileri düş → net çalışma
    total_deduction_before_table_min = lunch_deduction_min
    provisional_net_hours = target_hours - (total_deduction_before_table_min / 60)

    # 4. Kesinti tablosundan ek kesinti bul
    table_deduction_min = calc_break_deduction_table(provisional_net_hours)

    # 5. Toplam kesinti
    total_deduction_min = total_deduction_before_table_min + table_deduction_min

    # 6. Çıkış saatini hesapla
    total_duration_min = int(target_hours * 60) + total_deduction_min
    raw_exit = effective_entry + timedelta(minutes=total_duration_min)

    # 7. Çıkış filtresini uygula
    effective_exit = apply_exit_filter(raw_exit)

    # 8. Gerçek çalışma süresi
    actual_work_min = (effective_exit - effective_entry).seconds // 60

    return {
        "raw_entry"            : format_hhmm(raw_entry),
        "effective_entry"      : format_hhmm(effective_entry),
        "entry_adjusted"       : raw_entry != effective_entry,
        "target_hours"         : target_hours,
        "total_outside_min"    : total_outside_min,
        "lunch_deduction_min"  : lunch_deduction_min,
        "table_deduction_min"  : table_deduction_min,
        "total_deduction_min"  : total_deduction_min,
        "raw_exit"             : format_hhmm(raw_exit),
        "effective_exit"       : format_hhmm(effective_exit),
        "exit_adjusted"        : raw_exit != effective_exit,
        "actual_work_min"      : actual_work_min,
        "actual_work_hours"    : actual_work_min / 60,
        "is_valid"             : effective_exit > effective_entry,
    }


# ─────────────────────────────────────────────
# STREAMLIT ARAYÜZÜ
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Mesai Hesaplama Aracı",
    page_icon="🕐",
    layout="wide",
)

# ── CSS ──────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Başlık alanı */
    .hero {
        background: linear-gradient(135deg, #1a1f36 0%, #2d3561 100%);
        border-radius: 16px;
        padding: 28px 32px 22px;
        margin-bottom: 28px;
        color: white;
    }
    .hero h1 { margin: 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.5px; }
    .hero p  { margin: 6px 0 0; font-size: 0.9rem; opacity: 0.7; }

    /* Kart */
    .card {
        background: #ffffff;
        border: 1px solid #e8eaf0;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .card-title {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #8b92a5;
        margin-bottom: 12px;
    }

    /* Kural rozeti */
    .rule-badge {
        display: inline-block;
        background: #f0f3ff;
        color: #3d4fd6;
        border-radius: 6px;
        padding: 3px 9px;
        font-size: 0.75rem;
        font-weight: 500;
        margin: 3px 3px 3px 0;
    }

    /* Metric override */
    [data-testid="metric-container"] {
        background: #f8f9fc;
        border: 1px solid #e8eaf0;
        border-radius: 12px;
        padding: 14px 18px !important;
    }
    [data-testid="metric-container"] label {
        font-size: 0.72rem !important;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #8b92a5 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        color: #1a1f36 !important;
    }

    /* Çıkış saati vurgu */
    .exit-time-box {
        background: linear-gradient(135deg, #2d3561, #4a6cf7);
        border-radius: 14px;
        padding: 22px 28px;
        color: white;
        text-align: center;
    }
    .exit-time-box .label { font-size: 0.75rem; opacity: 0.75; letter-spacing: 0.1em; text-transform: uppercase; }
    .exit-time-box .time  { font-size: 3.2rem; font-weight: 700; letter-spacing: -1px; }
    .exit-time-box .sub   { font-size: 0.82rem; opacity: 0.7; margin-top: 4px; }

    /* Sidebar */
    [data-testid="stSidebar"] { background: #f4f5f9; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stTimeInput label {
        font-size: 0.8rem;
        font-weight: 600;
        color: #3d4555;
    }

    /* Uyarı */
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
</style>
""", unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────
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
        help="İşyerine giriş yaptığınız saat.",
    )

    st.markdown("---")

    total_outside = st.number_input(
        "Toplam Dışarıda Kalınan Süre (dakika)",
        min_value=0,
        max_value=300,
        value=60,
        step=5,
        help="Öğle arası + diğer tüm molalar toplamı (dakika cinsinden).",
    )

    st.markdown("---")

    target_label = st.selectbox(
        "Hedeflenen Mesai Kategorisi",
        options=list(TARGET_CATEGORIES.keys()),
        index=1,
        help="Ulaşmak istediğiniz mesai seviyesi.",
    )

    st.markdown("---")
    st.markdown("""
    <div class="card-title">Sabit Kurallar</div>
    <span class="rule-badge">07:00–08:00 → 08:00</span>
    <span class="rule-badge">17:00–18:00 → 17:00</span>
    <span class="rule-badge">60 dk ücretsiz öğle</span>
    <span class="rule-badge">≤4sa → 15dk kesinti</span>
    <span class="rule-badge">≤7.5sa → 30dk</span>
    <span class="rule-badge">≤11sa → 60dk</span>
    <span class="rule-badge">&gt;11sa → 90dk</span>
    """, unsafe_allow_html=True)

# ── Hesaplama ─────────────────────────────────
entry_str    = entry_time.strftime("%H:%M")
target_hours = TARGET_CATEGORIES[target_label]

result = calculate(
    raw_entry_str    = entry_str,
    total_outside_min= total_outside,
    target_hours     = target_hours,
)

# ── Sonuçlar ──────────────────────────────────
col_main, col_detail = st.columns([1, 1.6], gap="large")

with col_main:
    # Çıkış saati büyük gösterim
    if not result["is_valid"]:
        st.markdown("""
        <div class="warn-box">
        ⚠️ <strong>Geçersiz hesaplama:</strong> Hesaplanan çıkış saati, giriş saatinden önceye düşüyor.
        Lütfen giriş saatini veya mola süresini kontrol edin.
        </div>
        """, unsafe_allow_html=True)
    else:
        exit_note = ""
        if result["exit_adjusted"]:
            exit_note = f"(Ham: {result['raw_exit']} → filtre uygulandı)"

        st.markdown(f"""
        <div class="exit-time-box">
          <div class="label">Hesaplanan Çıkış Saati</div>
          <div class="time">{result['effective_exit']}</div>
          <div class="sub">{exit_note if exit_note else "Filtre uygulanmadı"}</div>
        </div>
        """, unsafe_allow_html=True)

    # Giriş bilgisi
    if result["entry_adjusted"]:
        st.markdown(f"""
        <div class="adj-note">
        ℹ️ Giriş saatiniz <strong>{result['raw_entry']}</strong>, 07:00–08:00 aralığında olduğu için
        <strong>{result['effective_entry']}</strong> olarak kabul edildi.
        </div>
        """, unsafe_allow_html=True)

with col_detail:
    st.markdown('<div class="card-title">Hesaplama Detayı</div>', unsafe_allow_html=True)

    r1, r2 = st.columns(2)
    r1.metric("Efektif Giriş",   result["effective_entry"])
    r2.metric("Hedef Mesai",     hours_to_hhmm(result["target_hours"]))

    r3, r4 = st.columns(2)
    r3.metric(
        "Öğle Kesintisi",
        f"{result['lunch_deduction_min']} dk",
        help=f"Dışarıda: {result['total_outside_min']} dk — İlk 60 dk ücretsiz",
    )
    r4.metric(
        "Tablo Kesintisi",
        f"{result['table_deduction_min']} dk",
        help="Net çalışma süresine göre kesinti tablosundan.",
    )

    r5, r6 = st.columns(2)
    r5.metric(
        "Toplam Kesinti",
        f"{result['total_deduction_min']} dk",
    )
    r6.metric(
        "Net Çalışma",
        hours_to_hhmm(result["actual_work_hours"]),
    )

# ── Kesinti Tablosu Bilgi Kartı ───────────────
st.markdown("---")
with st.expander("📋 Kesinti Tablosu & Kural Özeti", expanded=False):
    tc1, tc2 = st.columns(2)

    with tc1:
        st.markdown("**Kesinti Tablosu**")
        st.markdown("""
| Net Çalışma Süresi | Kesinti |
|---|---|
| ≤ 4 saat | 15 dakika |
| 4 – 7,5 saat | 30 dakika |
| 7,5 – 11 saat | 60 dakika |
| > 11 saat | 90 dakika |
""")

    with tc2:
        st.markdown("**Giriş/Çıkış Filtresi**")
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
        "**Öğle Arası:** 11:30–13:30 penceresi içindeki ilk 60 dakika ücretsizdir. "
        "Aşılan her dakika mesaiden düşülür. **Diğer molalar:** Tamamı mesaiden kesilir.",
        icon="🥗",
    )
