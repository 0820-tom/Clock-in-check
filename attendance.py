import streamlit as st
import pandas as pd

st.set_page_config(page_title="근태 누적 관리 시스템", layout="wide")

st.title("🗄️ 월간 근태 누적 분석 시스템")
st.info("파일을 업로드할 때마다 기존 데이터에 누적으로 합산됩니다.")

# --- 1. 초기 세션 상태 설정 (데이터 저장소) ---
if 'all_data' not in st.session_state:
    st.session_state['all_data'] = pd.DataFrame()

# 제외 대상 설정
EXCLUDE_NAMES = ['김기돈', '임덕상', '여기대', '김효정', '김운철', '윤희주']
EXCLUDE_KEYWORDS = ['사장', '이사', '대표', '본부장']

# --- 2. 사이드바 제어 ---
with st.sidebar:
    st.header("설정")
    if st.button("🔄 누적 데이터 초기화"):
        st.session_state['all_data'] = pd.DataFrame()
        st.rerun()

# --- 3. 파일 업로드 및 병합 ---
uploaded_file = st.file_uploader("근태 파일(XLS, XLSX, CSV)을 업로드하세요", type=['csv', 'xls', 'xlsx'])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            new_df = pd.read_csv(uploaded_file, encoding='cp949')
        else:
            new_df = pd.read_excel(uploaded_file)
            
        # 데이터 전처리
        for col in ['성명', '부서', '직급', '출근시각', '퇴근시각', '근무일자']:
            if col in new_df.columns:
                new_df[col] = new_df[col].astype(str).str.strip().replace(['nan', 'None', ':', 'nan:nan'], '')

        # 기존 데이터와 병합 및 중복 제거 (근무일자 + 성명 기준)
        if st.session_state['all_data'].empty:
            st.session_state['all_data'] = new_df
        else:
            combined = pd.concat([st.session_state['all_data'], new_df], ignore_index=True)
            # 날짜와 이름이 같은 중복 데이터는 최신 것으로 유지
            st.session_state['all_data'] = combined.drop_duplicates(subset=['근무일자', '성명'], keep='last')
            
        st.success(f"현재 총 {len(st.session_state['all_data'])}행의 데이터가 누적되었습니다.")

    except Exception as e:
        st.error(f"파일 분석 중 오류 발생: {e}")

# --- 4. 분석 로직 (누적된 전체 데이터 기준) ---
if not st.session_state['all_data'].empty:
    df = st.session_state['all_data']
    
    # 분석에 사용될 월 정보 추출 (가장 마지막 데이터 기준)
    target_month = "분석"
    sample_date = df['근무일자'].iloc[-1]
    if '.' in sample_date:
        target_month = sample_date.split('.')[1] + "월"

    results = {"출근 누락": [], "퇴근 누락": [], "연차상신 누락": [], "지각(10시↑)": []}

    for _, row in df.iterrows():
        name = row.get('성명', '')
        dept = row.get('부서', '')
        rank = row.get('직급', '')
        date = row.get('근무일자', '')
        in_t = row.get('출근시각', '')
        out_t = row.get('퇴근시각', '')

        # 제외 필터
        if name in EXCLUDE_NAMES or any(k in str(rank) for k in EXCLUDE_KEYWORDS) or any(k in str(dept) for k in EXCLUDE_KEYWORDS):
            continue

        # 분류
        if not in_t and not out_t:
            results["연차상신 누락"].append([date, name, dept, "-", "-", "기록 없음"])
        elif not in_t and out_t:
            results["출근 누락"].append([date, name, dept, "-", out_t, "퇴근만 기록"])
        elif in_t and not out_t:
            results["퇴근 누락"].append([date, name, dept, in_t, "-", "출근만 기록"])
        elif in_t:
            try:
                h, m = map(int, in_t.split(':')[:2])
                if h >= 10 and m > 0:
                    results["지각(10시↑)"].append([date, name, dept, in_t, out_t, f"{in_t} 출근"])
            except: pass

    # 결과 화면 출력
    st.markdown("---")
    cols = st.columns(2)
    summary_text = f"### {target_month} 근태 분석 요약 (누적)\n\n"

    for i, (category, data) in enumerate(results.items()):
        with cols[i % 2]:
            count = len(data)
            unique_people = len(set([d[1] for d in data]))
            st.subheader(f"📍 {category} ({unique_people}명/{count}건)")
            
            if data:
                # 날짜순 정렬하여 보여주기
                res_df = pd.DataFrame(data, columns=['날짜', '성명', '부서', '출근', '퇴근', '비고']).sort_values(by='날짜')
                st.dataframe(res_df, use_container_width=True)
                
                # 요약 텍스트 생성
                names = [f"{d[1]}({str(d[0]).split('.')[-1]}일)" for d in data]
                summary_text += f"* **{category}** : {unique_people}명/{count}건\n    * {', '.join(names)}\n"
            else:
                st.write("내역 없음")

    st.markdown("---")
    st.subheader("📝 누적 보고서용 요약 텍스트")
    st.text_area("그대로 복사하세요", value=summary_text, height=250)
