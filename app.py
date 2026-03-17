import streamlit as st
import pandas as pd
import re
from datetime import datetime

# ── 페이지 설정 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="근태 체크 마스터",
    page_icon="🕐",
    layout="wide",
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
    .metric-card.warn   { border-left-color: #e67e22; }
    .metric-card.danger { border-left-color: #e74c3c; }
    .metric-card.info   { border-left-color: #3498db; }
    .metric-label { font-size: 13px; color: #868e96; font-weight: 500; }
    .metric-value { font-size: 28px; font-weight: 700; color: #212529; margin-top: 2px; }
    .section-title {
        font-size: 15px; font-weight: 700; color: #343a40;
        padding: 10px 0 6px; border-bottom: 2px solid #dee2e6; margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ── 상수 및 설정 ─────────────────────────────────────────────────
_SKIP_NAMES = frozenset(['김기돈', '여기대', '임덕상', '김효정', '윤희주', '김운철'])
_EMPTY_VALS = {'', 'nan', 'None', 'NaN', 'none', '-', 'null'}

# 공휴일 설정 (YYYY-MM-DD 형식)
_HOLIDAYS = {
    '2024-01-01', '2024-02-09', '2024-02-12', '2024-03-01', 
    '2024-04-10', '2024-05-06', '2024-05-15', '2024-06-06',
    '2024-08-15', '2024-09-16', '2024-09-17', '2024-09-18', 
    '2024-10-03', '2024-10-09', '2024-12-25'
}

# ── 헬퍼 함수 ────────────────────────────────────────────────────
def _read_file(f) -> pd.DataFrame:
    name = f.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(f, encoding='cp949')
    else:
        # xls와 xlsx 모두 대응하기 위해 engine 옵션 제거 (자동 탐지)
        return pd.read_excel(f, header=0)

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip().replace('nan', '')
    return df

def _get_val(row, col_name: str, default_idx: int) -> str:
    if col_name and col_name in row.index:
        val = str(row[col_name]).strip()
        return '' if val in _EMPTY_VALS else val
    if 0 <= default_idx < len(row):
        val = str(row.iloc[default_idx]).strip()
        return '' if val in _EMPTY_VALS else val
    return ''

def _is_late(in_t: str) -> bool:
    try:
        nums = re.findall(r'\d+', str(in_t))
        if len(nums) < 2: return False
        return int(nums[0]) * 60 + int(nums[1]) > 600
    except:
        return False

def _day(date_str: str) -> str:
    """구분자에 상관없이 '일' 추출"""
    try:
        parts = re.split(r'[.\-/]', str(date_str))
        return parts[-1].zfill(2) + '일' if parts else ''
    except:
        return ''

def _is_workday(date_str: str) -> bool:
    """주말 및 공휴일 여부 판단"""
    try:
        # 다양한 날짜 형식을 표준 형식(YYYY-MM-DD)으로 변환 시도
        clean_date = re.sub(r'[.\-/]', '-', str(date_str))
        dt = pd.to_datetime(clean_date)
        
        # 1. 주말 체크 (5=토요일, 6=일요일)
        if dt.weekday() >= 5:
            return False
        # 2. 공휴일 체크
        if dt.strftime('%Y-%m-%d') in _HOLIDAYS:
            return False
        return True
    except:
        return True # 판별 불가 시 평일로 간주

# ── 세션 상태 ────────────────────────────────────────────────────
if 'records' not in st.session_state:
    st.session_state.records = pd.DataFrame()

# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정 및 업로드")
    uploaded = st.file_uploader("근태 파일 업로드", type=['xls', 'xlsx', 'csv'])
    
    st.markdown("---")
    exclude_weekend = st.toggle("주말/공휴일 자동 제외", value=True)
    
    if st.button("🗑️ 데이터 초기화", use_container_width=True):
        st.session_state.records = pd.DataFrame()
        st.rerun()

# ── 파일 처리 ────────────────────────────────────────────────────
if uploaded:
    try:
        new_df = _clean(_read_file(uploaded))
        if st.session_state.records.empty:
            st.session_state.records = new_df
        else:
            combined = pd.concat([st.session_state.records, new_df], ignore_index=True)
            st.session_state.records = combined.drop_duplicates(subset=['근무일자', '성명'], keep='last')
        st.toast(f"✅ {uploaded.name} 처리 완료", icon="✅")
    except Exception as e:
        st.error(f"파일 읽기 오류: {e}")

# ── 분석 엔진 ────────────────────────────────────────────────────
def run_analysis(df: pd.DataFrame, skip: frozenset) -> dict:
    buckets = {"출근 누락": [], "퇴근 누락": [], "연차상신 누락": [], "지각": []}

    for _, row in df.iterrows():
        name  = _get_val(row, '성명',     7)
        date  = _get_val(row, '근무일자', 0)
        
        # 주말/공휴일 제외 로직 적용
        if exclude_weekend and not _is_workday(date):
            continue

        in_t  = _get_val(row, '출근시각', -1)
        out_t = _get_val(row, '퇴근시각', -1)
        gubun = _get_val(row, '근무구분', 3)
        vacat = _get_val(row, '연차승인', 4)
        biz   = _get_val(row, '출장', 5)

        if gubun != '정상근무' or name in skip or '[완료(승인)]' in vacat or biz:
            continue

        if not in_t and not out_t:
            buckets["연차상신 누락"].append([date, name, '-', '-', '기록 없음'])
        elif not in_t:
            buckets["출근 누락"].append([date, name, '-', out_t, '퇴근만 기록'])
        elif not out_t:
            buckets["퇴근 누락"].append([date, name, in_t, '-', '출근만 기록'])
        elif _is_late(in_t):
            buckets["지각"].append([date, name, in_t, out_t, f'{in_t} 지각'])

    return buckets

# ── 메인 화면 ────────────────────────────────────────────────────
st.title("🕐 근태 분석 대시보드")

if st.session_state.records.empty:
    st.info("사이드바에서 파일을 업로드해주세요.")
    st.stop()

results = run_analysis(st.session_state.records, _SKIP_NAMES)

# 요약 카드
st.markdown("<div class='section-title'>📊 분석 요약</div>", unsafe_allow_html=True)
cols = st.columns(4)
styles = ["danger", "warn", "info", "warn"]
for col, (label, data), style in zip(cols, results.items(), styles):
    people = len({d[1] for d in data})
    col.markdown(f"<div class='metric-card {style}'><div class='metric-label'>{label}</div><div class='metric-value'>{people}<span style='font-size:16px;color:#868e96'>명 / {len(data)}건</span></div></div>", unsafe_allow_html=True)

# 상세 탭
st.markdown("---")
tabs = st.tabs(["🔴 출근 누락", "🟠 퇴근 누락", "🔵 연차상신 누락", "🟡 지각"])
for tab, (key, data) in zip(tabs, results.items()):
    with tab:
        if data:
            res_df = pd.DataFrame(data, columns=['날짜', '성명', '출근', '퇴근', '비고']).sort_values('날짜')
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            csv = res_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(f"⬇️ {key} 다운로드", csv, f"{key}.csv", "text/csv")
        else:
            st.success("해당 내역 없음 ✅")

# 보고서 텍스트
st.markdown("---")
st.markdown("<div class='section-title'>📝 보고서 요약 텍스트</div>", unsafe_allow_html=True)
lines = [f"* **{label}** : {len({d[1] for d in data})}명 / {len(data)}건\n  * {', '.join([f'{d[1]}({_day(d[0])})' for d in data])}" if data else f"* **{label}** : 0건" for label, data in results.items()]
st.text_area("복사하여 사용하세요", value="\n".join(lines), height=180, label_visibility="collapsed")
