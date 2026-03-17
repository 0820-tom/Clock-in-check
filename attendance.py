import streamlit as st
import pandas as pd

st.set_page_config(page_title="근태 누적 관리 시스템", layout="wide")

st.title("🗄️ 월간 근태 누적 분석 시스템")
st.info("XLS, XLSX, CSV 파일을 업로드하면 기존 데이터에 누적됩니다.")

# --- 1. 초기 세션 상태 설정 (누적 저장소) ---
if 'all_data' not in st.session_state:
    st.session_state['all_data'] = pd.DataFrame()

# 제외 대상 설정 (UI에 표시하지 않음)
_EXCLUDE_NAMES = {'김기돈', '여기대', '임덕상', '김효정', '윤희주', '김운철'}

# --- 2. 사이드바 제어 ---
with st.sidebar:
    st.header("⚙️ 관리")
    if st.button("🔄 누적 데이터 초기화"):
        st.session_state['all_data'] = pd.DataFrame()
        st.rerun()

# --- 3. 파일 업로드 및 읽기 ---
uploaded_file = st.file_uploader("근태 파일(XLS, XLSX, CSV)을 업로드하세요", type=['csv', 'xls', 'xlsx'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            new_df = pd.read_csv(uploaded_file, encoding='cp949')
        elif uploaded_file.name.endswith('.xls'):
            new_df = pd.read_excel(uploaded_file, engine='xlrd', header=0)
        else:
            new_df = pd.read_excel(uploaded_file, engine='openpyxl', header=0)

        # 컬럼 인덱스 기반으로 필요한 컬럼 이름 확인 (A=0 ~ H=7)
        cols = new_df.columns.tolist()

        # 컬럼명이 있으면 이름 기반, 없으면 인덱스 기반으로 접근하는 헬퍼
        def get_col(df, name, idx):
            """컬럼명으로 먼저 찾고, 없으면 위치 인덱스로 접근"""
            if name in df.columns:
                return df[name].astype(str).str.strip()
            elif idx < len(df.columns):
                return df.iloc[:, idx].astype(str).str.strip()
            else:
                return pd.Series([''] * len(df))

        # 각 컬럼 매핑
        # E셀(index 4): 연차/휴가 승인 여부
        # F셀(index 5): 출장 여부
        # H셀(index 7): 성명
        col_names = {
            '근무일자': ('근무일자', 0),
            '성명':     ('성명',     7),  # H셀
            '부서':     ('부서',     -1),
            '직급':     ('직급',     -1),
            '출근시각': ('출근시각', -1),
            '퇴근시각': ('퇴근시각', -1),
            '연차승인': (None,       4),  # E셀: [완료(승인)] 포함 여부
            '출장':     (None,       5),  # F셀: 값 있으면 출장
        }

        # 데이터 전처리
        clean_cols = ['성명', '부서', '직급', '출근시각', '퇴근시각', '근무일자']
        for col in clean_cols:
            if col in new_df.columns:
                new_df[col] = new_df[col].astype(str).str.strip().replace(
                    ['nan', 'None', ':', 'nan:nan'], ''
                )

        # 데이터 누적 및 중복 제거
        if st.session_state['all_data'].empty:
            st.session_state['all_data'] = new_df
        else:
            combined = pd.concat([st.session_state['all_data'], new_df], ignore_index=True)
            key_cols = [c for c in ['근무일자', '성명'] if c in combined.columns]
            if key_cols:
                st.session_state['all_data'] = combined.drop_duplicates(subset=key_cols, keep='last')
            else:
                st.session_state['all_data'] = combined

        st.success(f"현재 총 {len(st.session_state['all_data'])}행의 데이터가 누적되었습니다.")

    except ImportError as e:
        st.error(f"❗ 엔진 설치가 필요합니다: {e}")
        st.info("터미널에 'pip install xlrd openpyxl'을 입력하고 엔터를 눌러주세요.")
    except Exception as e:
        st.error(f"⚠️ 파일 분석 중 오류 발생: {e}")

# --- 4. 누적 데이터 분석 및 출력 ---
if not st.session_state['all_data'].empty:
    df = st.session_state['all_data']
    total_cols = df.columns.tolist()

    def safe_get(row, name, idx):
        """행에서 컬럼명 또는 위치로 값을 가져옴"""
        if name and name in row.index:
            return str(row[name]).strip()
        if idx >= 0 and idx < len(row):
            return str(row.iloc[idx]).strip()
        return ''

    def is_empty(val):
        return val in ('', 'nan', 'None', 'NaN', '-')

    # 월 정보 자동 추출 (안정적인 방식)
    target_month = "분석"
    if '근무일자' in df.columns:
        valid_dates = df['근무일자'].dropna().astype(str)
        valid_dates = valid_dates[valid_dates.str.match(r'\d{4}\.\d{2}')]
        if not valid_dates.empty:
            target_month = valid_dates.iloc[0].split('.')[1] + "월"

    results = {
        "출근 누락":      [],
        "퇴근 누락":      [],
        "연차상신 누락":  [],
        "지각(10시↑)":   [],
    }

    for _, row in df.iterrows():
        name    = safe_get(row, '성명',     7)   # H셀
        dept    = safe_get(row, '부서',    -1)
        rank    = safe_get(row, '직급',    -1)
        date    = safe_get(row, '근무일자', 0)
        in_t    = safe_get(row, '출근시각',-1)
        out_t   = safe_get(row, '퇴근시각',-1)
        d_val   = safe_get(row, None,       3)   # D셀: 근무 구분
        e_val   = safe_get(row, None,       4)   # E셀: 연차 승인
        f_val   = safe_get(row, None,       5)   # F셀: 출장

        # ── D열이 "정상근무"인 행만 분석 대상 ──
        if d_val != '정상근무':
            continue

        # ── 제외 필터 (화면에 표시하지 않음) ──
        if name in _EXCLUDE_NAMES:
            continue

        # ── 연차 처리: E셀에 [완료(승인)] 포함 시 정상 처리 ──
        if '[완료(승인)]' in e_val:
            continue

        # ── 출장 처리: F셀에 값이 있으면 정상 처리 ──
        if not is_empty(f_val):
            continue

        # ── 빈값 정규화 ──
        if is_empty(in_t):
            in_t = ''
        if is_empty(out_t):
            out_t = ''

        # ── 이상 내역 분류 ──
        if not in_t and not out_t:
            results["연차상신 누락"].append([date, name, dept, "-", "-", "기록 없음"])
        elif not in_t and out_t:
            results["출근 누락"].append([date, name, dept, "-", out_t, "퇴근만 존재"])
        elif in_t and not out_t:
            results["퇴근 누락"].append([date, name, dept, in_t, "-", "출근만 존재"])
        elif in_t:
            # 지각 판단: 10:01 이상 (10:00 정각은 정상, 10:01부터 지각)
            try:
                parts = in_t.split(':')
                h, m = int(parts[0]), int(parts[1])
                total_minutes = h * 60 + m
                if total_minutes > 600:  # 10:00 = 600분, 초과 시 지각
                    results["지각(10시↑)"].append([date, name, dept, in_t, out_t, f"{in_t} 출근"])
            except Exception:
                pass

    # ── 결과 대시보드 출력 ──
    st.markdown("---")
    cols_ui = st.columns(2)
    summary_text = f"### {target_month} 근태 분석 요약 (누적 결과)\n\n"

    for i, (category, data) in enumerate(results.items()):
        with cols_ui[i % 2]:
            count = len(data)
            unique_people = len(set([d[1] for d in data]))
            st.subheader(f"📍 {category} ({unique_people}명/{count}건)")

            if data:
                res_df = pd.DataFrame(
                    data, columns=['날짜', '성명', '부서', '출근', '퇴근', '비고']
                ).sort_values(by='날짜')
                st.dataframe(res_df, use_container_width=True)

                names_list = [f"{d[1]}({str(d[0]).split('.')[-1]}일)" for d in data]
                summary_text += f"* **{category}** : {unique_people}명/{count}건\n    * {', '.join(names_list)}\n"
            else:
                st.write("이상 내역 없음")

    st.markdown("---")
    st.subheader(f"📝 {target_month} 보고서용 요약 텍스트")
    st.text_area("복사해서 사용하세요", value=summary_text, height=250)
