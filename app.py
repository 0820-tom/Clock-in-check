import streamlit as st
import pandas as pd

# ── 페이지 설정 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="근태 체크",
    page_icon="🕐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 스타일 ───────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

    .metric-card {
        background: #f8f9fa;
        border-left: 4px solid #495057;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 8px;
    }
    .metric-card.warn  { border-left-color: #e67e22; }
    .metric-card.danger{ border-left-color: #e74c3c; }
    .metric-card.info  { border-left-color: #3498db; }
    .metric-card.ok    { border-left-color: #2ecc71; }

    .metric-label { font-size: 13px; color: #868e96; font-weight: 500; }
    .metric-value { font-size: 28px; font-weight: 700; color: #212529; margin-top: 2px; }

    .section-title {
        font-size: 15px;
        font-weight: 700;
        color: #343a40;
        padding: 10px 0 6px;
        border-bottom: 2px solid #dee2e6;
        margin-bottom: 12px;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    .stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── 상수 ─────────────────────────────────────────────────────────
_SKIP_NAMES = frozenset(['김기돈', '여기대', '임덕상', '김효정', '윤희주', '김운철'])

# ── 세션 상태 ────────────────────────────────────────────────────
if 'records' not in st.session_state:
    st.session_state.records = pd.DataFrame()

# ── 헬퍼 ─────────────────────────────────────────────────────────
_EMPTY = {'', 'nan', 'None', 'NaN', 'none', '-', 'null'}

def _str(val) -> str:
    s = str(val).strip()
    return '' if s in _EMPTY else s

def _col(row, name: str, idx: int) -> str:
    """컬럼명 우선, 없으면 위치 인덱스로 접근"""
    if name and name in row.index:
        return _str(row[name])
    if 0 <= idx < len(row):
        return _str(row.iloc[idx])
    return ''

def _is_late(in_t: str) -> bool:
    """10:01 이상이면 지각"""
    try:
        h, m = int(in_t.split(':')[0]), int(in_t.split(':')[1])
        return h * 60 + m > 600
    except Exception:
        return False

def _month_label(df: pd.DataFrame) -> str:
    if '근무일자' not in df.columns:
        return "분석"
    dates = df['근무일자'].dropna().astype(str)
    dates = dates[dates.str.match(r'\d{4}\.\d{2}')]
    if dates.empty:
        return "분석"
    return dates.iloc[0].split('.')[1] + "월"

def _read_file(f) -> pd.DataFrame:
    name = f.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(f, encoding='cp949')
    elif name.endswith('.xls'):
        return pd.read_excel(f, engine='xlrd', header=0)
    else:
        return pd.read_excel(f, engine='openpyxl', header=0)

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    targets = ['성명', '부서', '직급', '출근시각', '퇴근시각', '근무일자']
    for col in targets:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(list(_EMPTY), '')
    return df

# ── 분석 엔진 ────────────────────────────────────────────────────
def analyze(df: pd.DataFrame) -> dict:
    buckets = {
        "출근 누락":     [],
        "퇴근 누락":     [],
        "연차상신 누락": [],
        "지각":          [],
    }

    for _, row in df.iterrows():
        # 기본 필드
        name  = _col(row, '성명',     7)   # H열
        dept  = _col(row, '부서',    -1)
        date  = _col(row, '근무일자', 0)   # A열
        in_t  = _col(row, '출근시각',-1)
        out_t = _col(row, '퇴근시각',-1)
        d_val = _col(row, None,       3)   # D열: 근무구분
        e_val = _col(row, None,       4)   # E열: 연차승인
        f_val = _col(row, None,       5)   # F열: 출장

        # ① D열 = "정상근무" 인 행만 처리
        if d_val != '정상근무':
            continue

        # ② 제외 명단
        if name in _SKIP_NAMES:
            continue

        # ③ 연차 승인
        if '[완료(승인)]' in e_val:
            continue

        # ④ 출장 (F열에 값 있으면)
        if f_val:
            continue

        # ⑤ 분류
        if not in_t and not out_t:
            buckets["연차상신 누락"].append((date, name, dept, '-', '-', '기록 없음'))
        elif not in_t:
            buckets["출근 누락"].append((date, name, dept, '-', out_t, '퇴근만 존재'))
        elif not out_t:
            buckets["퇴근 누락"].append((date, name, dept, in_t, '-', '출근만 존재'))
        elif _is_late(in_t):
            buckets["지각"].append((date, name, dept, in_t, out_t, f'{in_t} 출근'))

    return buckets

# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🕐 근태 체크")
    st.markdown("---")
    uploaded = st.file_uploader(
        "근태 파일 업로드",
        type=['xls', 'xlsx', 'csv'],
        help="일일근태등록 엑셀 파일을 올려주세요"
    )
    st.markdown("---")
    if st.button("🗑️ 누적 데이터 초기화", use_container_width=True):
        st.session_state.records = pd.DataFrame()
        st.rerun()

    if not st.session_state.records.empty:
        st.caption(f"누적 행 수: **{len(st.session_state.records):,}**")

# ── 파일 처리 ────────────────────────────────────────────────────
if uploaded:
    try:
        new_df = _clean(_read_file(uploaded))

        if st.session_state.records.empty:
            st.session_state.records = new_df
        else:
            combined = pd.concat([st.session_state.records, new_df], ignore_index=True)
            key_cols = [c for c in ['근무일자', '성명'] if c in combined.columns]
            st.session_state.records = (
                combined.drop_duplicates(subset=key_cols, keep='last')
                if key_cols else combined
            )

        st.toast(f"✅ {uploaded.name} 업로드 완료 — 총 {len(st.session_state.records):,}행", icon="✅")

    except ImportError as e:
        st.error(f"라이브러리 오류: {e}")
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")

# ── 메인 화면 ────────────────────────────────────────────────────
st.markdown("## 🕐 근태 누적 분석")

if st.session_state.records.empty:
    st.info("왼쪽 사이드바에서 근태 파일을 업로드하면 분석 결과가 표시됩니다.")
    st.stop()

df      = st.session_state.records
month   = _month_label(df)
buckets = analyze(df)

# 요약 카드
st.markdown(f"<div class='section-title'>📊 {month} 요약</div>", unsafe_allow_html=True)

CARD_STYLES = {
    "출근 누락":     "danger",
    "퇴근 누락":     "warn",
    "연차상신 누락": "info",
    "지각":          "warn",
}

cols = st.columns(4)
for col, (label, data) in zip(cols, buckets.items()):
    people = len({d[1] for d in data})
    style  = CARD_STYLES[label]
    col.markdown(f"""
    <div class='metric-card {style}'>
        <div class='metric-label'>{label}</div>
        <div class='metric-value'>{people}<span style='font-size:16px;color:#868e96;font-weight:400'>명 / {len(data)}건</span></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# 상세 테이블
COLS = ['날짜', '성명', '부서', '출근', '퇴근', '비고']

tab1, tab2, tab3, tab4 = st.tabs(["🔴 출근 누락", "🟠 퇴근 누락", "🔵 연차상신 누락", "🟡 지각"])

for tab, key in zip([tab1, tab2, tab3, tab4], buckets):
    with tab:
        data = buckets[key]
        if data:
            result_df = pd.DataFrame(data, columns=COLS).sort_values('날짜')
            st.dataframe(result_df, use_container_width=True, hide_index=True)
        else:
            st.success("이상 내역 없음 ✅")

# 보고서 텍스트
st.markdown("---")
st.markdown(f"<div class='section-title'>📝 {month} 보고서용 텍스트</div>", unsafe_allow_html=True)

lines = [f"### {month} 근태 분석 요약\n"]
for label, data in buckets.items():
    people = len({d[1] for d in data})
    lines.append(f"* **{label}** : {people}명 / {len(data)}건")
    if data:
        items = [f"{d[1]}({str(d[0]).split('.')[-1]}일)" for d in data]
        lines.append(f"  * {', '.join(items)}")

st.text_area("복사해서 사용하세요", value="\n".join(lines), height=220, label_visibility="collapsed")
